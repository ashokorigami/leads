"""Re-run the full pipeline over every company that has a draft awaiting approval.

Why: on 2026-09-20 the queue held 54 drafts whose research was 5-6 weeks old.
Most triggers were job postings; a posting that has since been filled is a
claim the prospect can falsify in one click. Approving a stale draft is worse
than writing none.

pipeline.run_one() already does the right thing on a re-run: newest research
wins in v_sendable, a rewritten draft goes back to approved=NULL, and a company
that no longer qualifies is stage=rejected. What it does NOT do is withdraw
the OLD pending drafts of a company that fresh research rejected - those would
sit in the queue looking approvable. This tool does that afterwards, marking
them approved=FALSE with approved_by=rerun, so the operator can still see
what was withdrawn and why.

    python3 tools/rerun_pending.py            # dry run: lists the domains
    python3 tools/rerun_pending.py --apply
"""
import sys
from datetime import date

sys.path.insert(0, "/opt/origami-outbound/src")

import pipeline
from config import db, SCORE_THRESHOLD

APPLY = "--apply" in sys.argv
TAG = f"rerun-{date.today().isoformat()}"

PENDING_DOMAINS = """
    SELECT DISTINCT c.domain
    FROM emails e
    JOIN prospects p ON p.id = e.prospect_id
    JOIN companies c ON c.id = p.company_id
    WHERE e.approved IS NULL
    ORDER BY c.domain"""

with db() as conn, conn.cursor() as cur:
    cur.execute(PENDING_DOMAINS)
    domains = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT count(*) FROM emails WHERE approved IS NULL")
    pending_before = cur.fetchone()[0]

print(f"{len(domains)} companies behind {pending_before} pending drafts")
for d in domains:
    print(f"  {d}")
if not APPLY:
    print("\ndry run - pass --apply to spend credits")
    raise SystemExit

print("\nrunning pipeline:")
tally = pipeline.run(domains)
print("\noutcome tally:")
for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
    print(f"  {v:>4}  {k}")

# Withdraw pending drafts whose company now fails the gate on its NEWEST research.
with db() as conn, conn.cursor() as cur:
    cur.execute("""
        WITH latest AS (
            SELECT DISTINCT ON (company_id) company_id, score, disqualify_reason
            FROM research ORDER BY company_id, created_at DESC, id DESC)
        UPDATE emails e SET approved=FALSE, approved_by=%s, approved_at=now()
        FROM prospects p JOIN companies c ON c.id = p.company_id
        JOIN latest l ON l.company_id = c.id
        WHERE e.prospect_id = p.id AND e.approved IS NULL
          AND (l.score < %s OR l.disqualify_reason IS NOT NULL)
        RETURNING c.domain, l.score, l.disqualify_reason""",
        (TAG, SCORE_THRESHOLD))
    withdrawn = cur.fetchall()
    cur.execute("SELECT count(*) FROM emails WHERE approved IS NULL")
    pending_after = cur.fetchone()[0]

print(f"\nwithdrawn {len(withdrawn)} stale drafts (company no longer qualifies):")
for dom, score, why in withdrawn:
    print(f"  {dom:<28} score {score}  {why or ""}")
print(f"\npending drafts: {pending_before} before -> {pending_after} after")
print("Verify in the database, not from this line.")
