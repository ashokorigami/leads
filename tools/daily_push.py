"""Top up each rep's Instantly campaign to ~25 queued leads, once a day.

Each rep campaign sends at most 25/day (one mailbox each). This counts the leads
already queued but not yet contacted in each origami-<rep> campaign and pushes
just enough approved drafts signed by that rep to bring it back to TARGET.

Fails CLOSED on deliverability: if the bounce rate across the origami-*
campaigns is over the bar (see SMALL_*/LARGE_*), or the analytics call does not
return the fields it needs, it pushes nothing and says why. Each address is
re-verified just before it is pushed; invalid ones are unapproved and suppressed.

    python3 tools/daily_push.py            # dry run
    python3 tools/daily_push.py --apply

Run it from /opt/origami-outbound, never from /tmp (LESSONS.md sec.8).
"""
import sys

sys.path.insert(0, "/opt/origami-outbound/src")

import sender
from sender import db

TARGET = 25
# Two bars. On a small sample one bounce moves the rate a lot: 28 Oct, 2 of 45
# (4.4%) would have stopped all sending under a flat 3%, though 2 in 45 is
# consistent with a ~2% true rate. So: >5% stops from 20 sent; >3% from 100.
SMALL_N, SMALL_MAX = 20, 0.05
LARGE_N, LARGE_MAX = 100, 0.03
APPLY = "--apply" in sys.argv


def campaigns() -> dict[str, dict]:
    """origami-<rep> and origami-<rep>-<region>, keyed by the full suffix."""
    items = sender._req("GET", "/campaigns", params={"limit": 100})["items"]
    return {c["name"][len("origami-"):]: c for c in items if c["name"].startswith("origami-")}


def queued(campaign_id: str) -> int:
    n, cur = 0, None
    while True:
        body = {"campaign": campaign_id, "limit": 100}
        if cur:
            body["starting_after"] = cur
        d = sender._req("POST", "/leads/list", json=body)
        n += sum(1 for l in d["items"] if not l.get("timestamp_last_contact"))
        cur = d.get("next_starting_after")
        if not cur or not d["items"]:
            return n


# The gate judges only addresses re-verified at push time - sends.id >= this.
# 29 Oct (Ashok approved): the all-time rate (4/70, 5.7%) was set entirely by
# 28 Oct pushes made before push-time re-verify existed; the 13-lead
# re-verified test batch (sends 91-103) went out with 0 bounces. All-time can
# never fall while the gate is shut, so judging it would stop sending for good.
FIRST_VERIFIED_SEND_ID = 91


def bounce_gate(camps: dict[str, dict]) -> str | None:
    """Return a reason to stop, or None if it is safe to push."""
    sent = bounced = 0
    for c in camps.values():               # all-time, for the log only
        a = sender._req("GET", "/campaigns/analytics", params={"id": c["id"]})
        a = (a[0] if a else {}) if isinstance(a, list) else a
        sent += a.get("emails_sent_count") or 0
        bounced += a.get("bounced_count") or 0
    print(f"all time (Instantly): {bounced} bounced / {sent} sent")
    try:
        sender.sync_sends()
    except Exception as ex:                # fail closed: stale outcomes can hide bounces
        return f"could not sync send outcomes from Instantly: {type(ex).__name__}: {ex}"
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*) FILTER (WHERE status IN ('sent','bounced')),
                              count(*) FILTER (WHERE status = 'bounced')
                       FROM sends WHERE id >= %s""", (FIRST_VERIFIED_SEND_ID,))
        sent, bounced = cur.fetchone()
    rate = bounced / sent if sent else 0.0
    print(f"deliverability (re-verified sends): {bounced} bounced / {sent} sent = {rate:.1%}")
    if sent >= LARGE_N and rate > LARGE_MAX:
        return f"bounce rate {rate:.1%} > {LARGE_MAX:.0%} over {sent} sent"
    if sent >= SMALL_N and rate > SMALL_MAX:
        return f"bounce rate {rate:.1%} > {SMALL_MAX:.0%} over {sent} sent"
    return None

def main() -> None:
    camps = campaigns()
    stop = bounce_gate(camps)
    if stop:
        print("NOT PUSHING:", stop)
        sys.exit(1)

    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT full_name FROM reps WHERE active")
        reps = [(n, n.split()[0].lower()) for (n,) in cur.fetchall()]
        cur.execute("""
            SELECT e.id, e.body, p.email, p.company_id FROM emails e
            JOIN prospects p ON p.id = e.prospect_id
            WHERE e.approved IS TRUE
              AND NOT EXISTS (SELECT 1 FROM sends s WHERE s.email_id = e.id)
              AND NOT EXISTS (SELECT 1 FROM suppression x
                               WHERE x.kind = 'email' AND x.value = lower(p.email))"""
            + sender.COMPANY_NOT_CONTACTED + """
            ORDER BY e.id""")
        pending: dict[str, list[int]] = {}
        address: dict[int, str] = {}
        seen: set[int] = set()
        for eid, body, email, company_id in cur.fetchall():
            if company_id in seen:
                continue
            seen.add(company_id)
            rep = sender._rep_for(body, reps)
            if rep:
                pending.setdefault(rep[1], []).append(eid)
                address[eid] = email

    # One mailbox per rep sends for every region's campaign, and the 25/day
    # cap is on the mailbox - so the target is per REP, summed over regions.
    # push_approved() routes each draft to the right regional campaign.
    queued_by_rep: dict[str, int] = {}
    for key, c in camps.items():
        rep = key.split("-")[0]
        queued_by_rep[rep] = queued_by_rep.get(rep, 0) + queued(c["id"])
    ids: list[int] = []
    invalid: list[int] = []
    for rep in sorted(set(queued_by_rep) | set(pending)):
        q = queued_by_rep.get(rep, 0)
        avail = pending.get(rep, [])
        need = max(0, TARGET - q)
        take: list[int] = []
        for eid in avail:
            if len(take) >= need:
                break
            # Verify at push time, not at research time: addresses age (both
            # 28 Oct bounces were 'verified' in Jul/Aug). Only 'invalid' is
            # dropped; catch-all and no-answer go ahead. Dry runs skip it -
            # each check costs Instantly credits.
            if APPLY and sender.verify_email(address[eid]) == "invalid":
                invalid.append(eid)
                continue
            take.append(eid)
        print(f"{rep:10s} queued {q:3d}  approved-unsent {len(avail):3d}  push {len(take)}")
        ids += take
    if invalid:
        with db() as conn, conn.cursor() as cur:
            for eid in invalid:
                cur.execute("""UPDATE emails SET approved = FALSE, approved_by = 'push-verify-invalid',
                               approved_at = now() WHERE id = %s""", (eid,))
                cur.execute("""INSERT INTO suppression (kind, value, reason)
                               VALUES ('email', lower(%s), 'push-verify-invalid')
                               ON CONFLICT (kind, value) DO NOTHING""", (address[eid],))
        print(f"dropped {len(invalid)} invalid address(es) at push time")
    left = sum(len(v) for v in pending.values()) - len(ids)
    print(f"total push {len(ids)}; approved drafts left after this: {left}")
    if left < 3 * TARGET:
        print(f"WARNING: under one day of drafts in reserve ({left} < {3 * TARGET}) - approve more in /queue")

    if not ids:
        return
    if not APPLY:
        print("dry run - re-run with --apply")
        return
    res = sender.push_approved(limit=len(ids), only_ids=ids)
    print("pushed", res["pushed"], "failed", res["failed"])
    # Instantly marks a campaign completed (status 3) once every lead has been
    # contacted; 5 of 6 were completed on 29 Oct. New leads in a completed
    # campaign need it reactivated (measured 29 Oct: /activate on a completed
    # campaign returns it to 1 and it stays there). Only 3 is reactivated -
    # status 2 is the emergency pause and must stay put.
    for cid in set(res["campaigns"].values()):
        st = sender._req("GET", f"/campaigns/{cid}").get("status")
        if st == 3:
            st = sender.activate_campaign(cid).get("status")
            print(f"reactivated completed campaign {cid} -> status {st}")
        if st != 1:
            print(f"WARNING: campaign {cid} has status {st} (1=active, 2=paused, 3=completed) "
                  f"after the push - its new leads will not send")


if __name__ == "__main__":
    main()
