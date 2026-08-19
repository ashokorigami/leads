"""Push approved emails into Instantly, and pull replies back out.

Instantly owns delivery, mailbox rotation and the warmup pool. We own who to
write to and what to say. This module is the seam between the two.

Nothing here sends anything by itself: only rows in `emails` with approved=TRUE
are ever pushed, so a human gate sits in front of the send path by construction.
"""
import json
import httpx
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


def push_approved(limit: int = 50, only_ids: list[int] | None = None) -> dict:
    """Send approved, unsent emails to Instantly as leads with their own
    personalised body. Marks a row in `sends` so nothing is pushed twice.

    only_ids restricts the push to specific emails.id values. Without it there
    was no way to send a SUBSET: the first real call would have pushed every
    approved draft at once, so neither a single-address rehearsal nor a
    controlled ramp (15 on day one, not "up to 50") was expressible.

    Raises if no mailbox is live. The mailbox join is an INNER join, so with
    zero live mailboxes the whole select returned no rows and this function
    returned {"pushed": 0, "failed": 0} - a silent success that sent nothing.
    Measured 19 Aug: 0 rows through the real query, 26 with the mailbox join
    removed. A launch that reports success and sends nothing is worse than one
    that fails, so this now refuses rather than returning a clean zero.
    """
    pushed, failed = 0, 0
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM mailboxes WHERE status='live'")
        if not cur.fetchone()[0]:
            raise RuntimeError(
                "no mailbox has status='live' - push_approved would select zero "
                "rows and report success having sent nothing. Mark the warmed "
                "mailboxes live before sending.")
        cur.execute("""
            SELECT e.id, e.subject, e.body, p.email, p.first_name, p.last_name,
                   c.name, r.wedge, m.id
            FROM emails e
            JOIN prospects p ON p.id = e.prospect_id
            JOIN companies c ON c.id = p.company_id
            JOIN LATERAL (SELECT wedge FROM research WHERE company_id=c.id
                          ORDER BY created_at DESC LIMIT 1) r ON TRUE
            JOIN LATERAL (SELECT id FROM mailboxes WHERE status='live'
                          ORDER BY random() LIMIT 1) m ON TRUE
            WHERE e.approved IS TRUE
              AND NOT EXISTS (SELECT 1 FROM sends s WHERE s.email_id = e.id)
              AND (%s::bigint[] IS NULL OR e.id = ANY(%s::bigint[]))
            ORDER BY e.id
            LIMIT %s""", (only_ids, only_ids, limit))
        rows = cur.fetchall()

        campaigns: dict[str, str] = {}
        for eid, subj, body, email, fn, ln, co, wedge, mbid in rows:
            if wedge not in campaigns:
                campaigns[wedge] = ensure_campaign(f"origami-{wedge}")
            cid = campaigns[wedge]
            try:
                res = _req("POST", "/leads", json={
                    "campaign": cid, "email": email,
                    "first_name": fn, "last_name": ln, "company_name": co,
                    "personalization": body,
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
    return {"pushed": pushed, "failed": failed}


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
