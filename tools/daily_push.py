"""Top up each rep's Instantly campaign to ~25 queued leads, once a day.

Each rep campaign sends at most 25/day (one mailbox each). This counts the leads
already queued but not yet contacted in each origami-<rep> campaign and pushes
just enough approved drafts signed by that rep to bring it back to TARGET.

Fails CLOSED on deliverability: if the bounce rate across the origami-*
campaigns is above MAX_BOUNCE (with at least MIN_SENT sent), or the analytics
call does not return the fields it needs, it pushes nothing and says why.

    python3 tools/daily_push.py            # dry run
    python3 tools/daily_push.py --apply

Run it from /opt/origami-outbound, never from /tmp (LESSONS.md sec.8).
"""
import sys

sys.path.insert(0, "/opt/origami-outbound/src")

import sender
from sender import db

TARGET = 25
MAX_BOUNCE = 0.03
MIN_SENT = 20
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


def bounce_gate(camps: dict[str, dict]) -> str | None:
    """Return a reason to stop, or None if it is safe to push."""
    sent = bounced = 0
    for c in camps.values():
        a = sender._req("GET", "/campaigns/analytics", params={"id": c["id"]})
        a = a[0] if isinstance(a, list) else a
        if "emails_sent_count" not in a or "bounced_count" not in a:
            return f"analytics for {c['name']} lacks sent/bounce fields: {sorted(a)}"
        sent += a["emails_sent_count"] or 0
        bounced += a["bounced_count"] or 0
    rate = bounced / sent if sent else 0.0
    print(f"deliverability: {bounced} bounced / {sent} sent = {rate:.1%}")
    if sent >= MIN_SENT and rate > MAX_BOUNCE:
        return f"bounce rate {rate:.1%} > {MAX_BOUNCE:.0%}"
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
            SELECT e.id, e.body FROM emails e
            WHERE e.approved IS TRUE
              AND NOT EXISTS (SELECT 1 FROM sends s WHERE s.email_id = e.id)
            ORDER BY e.id""")
        pending: dict[str, list[int]] = {}
        for eid, body in cur.fetchall():
            rep = sender._rep_for(body, reps)
            if rep:
                pending.setdefault(rep[1], []).append(eid)

    # One mailbox per rep sends for every region's campaign, and the 25/day
    # cap is on the mailbox - so the target is per REP, summed over regions.
    # push_approved() routes each draft to the right regional campaign.
    queued_by_rep: dict[str, int] = {}
    for key, c in camps.items():
        rep = key.split("-")[0]
        queued_by_rep[rep] = queued_by_rep.get(rep, 0) + queued(c["id"])
    ids: list[int] = []
    for rep in sorted(set(queued_by_rep) | set(pending)):
        q = queued_by_rep.get(rep, 0)
        avail = pending.get(rep, [])
        take = avail[: max(0, TARGET - q)]
        print(f"{rep:10s} queued {q:3d}  approved-unsent {len(avail):3d}  push {len(take)}")
        ids += take
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


if __name__ == "__main__":
    main()
