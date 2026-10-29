"""Push approved emails into Instantly, and pull replies back out.

Instantly owns delivery, mailbox rotation and the warmup pool. We own who to
write to and what to say. This module is the seam between the two.

Nothing here sends anything by itself: only rows in `emails` with approved=TRUE
are ever pushed, so a human gate sits in front of the send path by construction.
"""
import json
import httpx
import time
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from config import ENV, db

BASE = "https://api.instantly.ai/api/v2"


def _client() -> httpx.Client:
    key = ENV.get("INSTANTLY_API_KEY", "")
    return httpx.Client(timeout=45.0, base_url=BASE,
                        headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json"})


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=2, max=20))
def _req(method: str, path: str, **kw) -> dict:
    with _client() as c:
        r = c.request(method, path, **kw)
        r.raise_for_status()
        return r.json() if r.content else {}


def list_accounts() -> list[dict]:
    return _req("GET", "/accounts", params={"limit": 50}).get("items", [])


def ensure_campaign(name: str) -> str:
    """One campaign per wedge, reused. Sequence body is templated per lead, so
    the campaign is just a container for scheduling and mailbox rotation."""
    for c in _req("GET", "/campaigns", params={"limit": 100}).get("items", []):
        if c.get("name") == name:
            return c["id"]
    return _req("POST", "/campaigns", json={
        "name": name,
        "campaign_schedule": {"schedules": [{
            "name": "weekdays",
            "timing": {"from": "09:00", "to": "16:00"},
            "days": {"1": True, "2": True, "3": True, "4": True, "5": True},
            "timezone": "America/New_York",
        }]},
    })["id"]


# Send window per region, in the recipient's morning. Instantly rejects some
# IANA names (America/New_York, Africa/Johannesburg) - the ones below were
# accepted on 28 Oct. Blantyre is UTC+2 with no DST, the same clock as Johannesburg.
REGIONS = {
    "us":     {"suffix": "",        "timezone": "America/Detroit",     "from": "09:00", "to": "16:00"},
    "africa": {"suffix": "-africa", "timezone": "Africa/Blantyre",     "from": "08:00", "to": "15:00"},
}
AFRICA = {"South Africa", "Nigeria", "Kenya", "Egypt", "Ghana", "Morocco", "Ethiopia",
          "Tanzania", "Uganda", "Rwanda", "Zambia", "Botswana", "Namibia", "Mauritius",
          "Ivory Coast", "Côte d'Ivoire", "Senegal", "Tunisia", "Algeria", "Angola",
          "Mozambique", "Zimbabwe", "Cameroon"}


def region_of(country: str | None) -> str:
    return "africa" if country in AFRICA else "us"


def ensure_rep_campaign(rep_key: str, mailbox: str, region: str = "us") -> str:
    """One Instantly campaign PER REP, sending only from that rep's mailbox.

    2026-10-28: the first real push was about to go through ensure_campaign(),
    which creates a campaign with no sequence, no sending accounts and no
    activation (Instantly had zero campaigns) - leads would have been accepted
    and nothing sent. And mailbox choice was random while the body is signed by
    one rep, so an email signed "Abhaya" could leave from manjula@ and its reply
    land in the wrong inbox. Pinning one campaign to one mailbox makes the From
    address match the signature by construction.

    Created PAUSED; activate_campaign() is a separate, deliberate step.
    """
    reg = REGIONS[region]
    name = f"origami-{rep_key}{reg['suffix']}"
    for c in _req("GET", "/campaigns", params={"limit": 100}).get("items", []):
        if c.get("name") == name:
            return c["id"]
    return _req("POST", "/campaigns", json={
        "name": name,
        "campaign_schedule": {"schedules": [{
            "name": "weekdays",
            "timing": {"from": reg["from"], "to": reg["to"]},
            "days": {"1": True, "2": True, "3": True, "4": True, "5": True},
            "timezone": reg["timezone"],
        }]},
        "sequences": [{"steps": [{"type": "email", "delay": 0, "variants": [
            {"subject": "{{subject}}", "body": "{{body}}"}]}]}],
        "email_list": [mailbox],
        "daily_limit": 25,
        "stop_on_reply": True,
        "text_only": True,
        "open_tracking": False,
        "link_tracking": False,
    })["id"]


def verify_email(email: str, wait_s: int = 120) -> str:
    """Instantly's verifier: 'verified', 'invalid', or 'pending' if it has not
    answered within wait_s. ~0.25 Instantly credits.

    Why at send time: on 28 Oct the first 45 sends bounced 2 - both Apollo
    'verified' in Jul/Aug research, both people since gone. Verification ages."""
    r = _req("POST", "/email-verification", json={"email": email})
    deadline = time.time() + wait_s
    while r.get("verification_status") == "pending" and time.time() < deadline:
        time.sleep(5)
        r = _req("GET", f"/email-verification/{email}")
    return r.get("verification_status") or "pending"


def activate_campaign(campaign_id: str) -> dict:
    return _req("POST", f"/campaigns/{campaign_id}/activate", json={})


def _rep_for(body: str, reps: list[tuple[str, str]]) -> tuple[str, str] | None:
    """(full_name, key) of the rep whose name signs this body - exactly one, or None."""
    hits = [r for r in reps if r[0] in body]
    return hits[0] if len(hits) == 1 else None


# One company, one cold email. 29 Oct: the first 15-lead test batch went
# entirely to companies emailed the day before (oldest drafts first = the same
# companies), incl. a colleague of someone who had unsubscribed that morning.
# Withdrawn before sending. Needs prospects aliased as p.
COMPANY_NOT_CONTACTED = """
  AND NOT EXISTS (SELECT 1 FROM sends s2 JOIN emails e2 ON e2.id = s2.email_id
                  JOIN prospects p2 ON p2.id = e2.prospect_id
                  WHERE p2.company_id = p.company_id
                    AND s2.status IN ('queued', 'sent', 'bounced'))
  AND NOT EXISTS (SELECT 1 FROM suppression x2
                  WHERE x2.kind = 'email' AND x2.reason = 'unsubscribe'
                    AND split_part(x2.value, '@', 2) = split_part(lower(p.email), '@', 2))"""


def push_approved(limit: int = 50, only_ids: list[int] | None = None) -> dict:
    """Send approved, unsent emails to Instantly as leads with their own
    personalised body, each into the campaign of the rep who signed it.
    Marks a row in `sends` so nothing is pushed twice.

    only_ids restricts the push to specific emails.id values (rehearsal, or a
    controlled ramp: 15 on day one, not "up to 50").

    Raises if no mailbox is live - a launch that reports success and sends
    nothing is worse than one that fails (measured 19 Aug: the old inner join
    returned 0 rows with no live mailbox and reported a clean zero).
    """
    pushed, failed = 0, 0
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, address FROM mailboxes WHERE status='live'")
        live = cur.fetchall()
        if not live:
            raise RuntimeError(
                "no mailbox has status='live' - push_approved would select zero "
                "rows and report success having sent nothing. Mark the warmed "
                "mailboxes live before sending.")
        cur.execute("SELECT full_name FROM reps WHERE active")
        reps = [(n, n.split()[0].lower()) for (n,) in cur.fetchall()]
        cur.execute("""
            SELECT e.id, e.subject, e.body, p.email, p.first_name, p.last_name, c.name, c.country, c.id
            FROM emails e
            JOIN prospects p ON p.id = e.prospect_id
            JOIN companies c ON c.id = p.company_id
            WHERE e.approved IS TRUE
              AND NOT EXISTS (SELECT 1 FROM sends s WHERE s.email_id = e.id)
              AND (%s::bigint[] IS NULL OR e.id = ANY(%s::bigint[]))""" + COMPANY_NOT_CONTACTED + """
            ORDER BY e.id""", (only_ids, only_ids))
        rows, seen = [], set()
        for r in cur.fetchall():        # and only one per company within this push
            if r[-1] not in seen and len(rows) < limit:
                seen.add(r[-1])
                rows.append(r[:-1])

        campaigns: dict[str, str] = {}
        for eid, subj, body, email, fn, ln, co, country in rows:
            rep = _rep_for(body, reps)
            mb = next(((i, a) for i, a in live
                       if rep and a.split("@")[0] == rep[1]), None)
            if rep is None or mb is None:
                why = "no single rep signature" if rep is None else f"no live mailbox for {rep[1]}"
                cur.execute("""INSERT INTO sends (email_id, mailbox_id, provider, status, error)
                               VALUES (%s,%s,'instantly','failed',%s)""",
                            (eid, live[0][0], f"not pushed: {why}"))
                failed += 1
                continue
            mbid, addr = mb
            try:
                key = f"{rep[1]}{REGIONS[region_of(country)]['suffix']}"
                if key not in campaigns:
                    campaigns[key] = ensure_rep_campaign(rep[1], addr, region_of(country))
                res = _req("POST", "/leads", json={
                    "campaign": campaigns[key], "email": email,
                    "first_name": fn, "last_name": ln, "company_name": co,
                    "custom_variables": {"subject": subj, "body": body},
                })
                cur.execute("""INSERT INTO sends (email_id, mailbox_id, provider,
                               provider_msg_id, status)
                               VALUES (%s,%s,'instantly',%s,'queued')""",
                            (eid, mbid, res.get("id")))
                pushed += 1
            except Exception as ex:
                cur.execute("""INSERT INTO sends (email_id, mailbox_id, provider,
                               status, error) VALUES (%s,%s,'instantly','failed',%s)""",
                            (eid, mbid, str(ex)[:300]))
                failed += 1
    return {"pushed": pushed, "failed": failed, "campaigns": campaigns}


def pull_replies(since_iso: str | None = None) -> int:
    """Fetch inbound mail from Instantly and hand each one to the classifier."""
    import replies as rep
    params = {"limit": 100, "email_type": "received"}
    if since_iso:
        params["start_date"] = since_iso
    items = _req("GET", "/emails", params=params).get("items", [])

    n = 0
    with db() as conn, conn.cursor() as cur:
        for m in items:
            frm = (m.get("from_address_email") or "").lower()
            cur.execute("SELECT id FROM replies WHERE from_email=%s AND subject=%s",
                        (frm, m.get("subject")))
            if cur.fetchone():
                continue                                   # already ingested
            cur.execute("SELECT id FROM prospects WHERE email=%s", (frm,))
            row = cur.fetchone()
            rep.ingest(frm, m.get("subject") or "",
                       m.get("body", {}).get("text") or "",
                       m.get("timestamp_created"),
                       prospect_id=row[0] if row else None)
            n += 1
    return n


# Instantly lead status: 1 active, 2 paused, 3 completed, -1 bounced,
# -2 unsubscribed, -3 skipped.
LEAD_BOUNCED = -1


def sync_sends() -> dict:
    """Copy each pushed lead's real outcome from Instantly into `sends`.

    2026-10-29: push_approved() writes status='queued' and nothing ever moved it
    on, so every row stayed queued with sent_at NULL and the digest reported
    "sent yesterday 0" the morning after 63 had gone out. Instantly is the only
    place that knows; this reads it back. A lead Instantly no longer has (deleted
    on re-verify) is left as it is rather than guessed at.
    """
    leads: dict[str, dict] = {}
    for c in _req("GET", "/campaigns", params={"limit": 100}).get("items", []):
        if not c["name"].startswith("origami-"):
            continue
        cur_id = None
        while True:
            body = {"campaign": c["id"], "limit": 100}
            if cur_id:
                body["starting_after"] = cur_id
            d = _req("POST", "/leads/list", json=body)
            for l in d["items"]:
                leads[l["id"]] = l
            cur_id = d.get("next_starting_after")
            if not cur_id or not d["items"]:
                break
    out = {"sent": 0, "bounced": 0, "unchanged": 0, "missing": 0}
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, provider_msg_id, status FROM sends
                       WHERE provider = 'instantly' AND status IN ('queued', 'sent')
                         AND provider_msg_id IS NOT NULL""")
        for sid, lead_id, status in cur.fetchall():
            l = leads.get(lead_id)
            if l is None:
                out["missing"] += 1
                continue
            when = l.get("timestamp_last_contact")
            new = "bounced" if l.get("status") == LEAD_BOUNCED else ("sent" if when else status)
            if new == status:
                out["unchanged"] += 1
                continue
            cur.execute("UPDATE sends SET status = %s, sent_at = COALESCE(sent_at, %s) WHERE id = %s",
                        (new, when, sid))
            out[new] += 1
    return out
