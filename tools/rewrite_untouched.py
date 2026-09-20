"""Rewrite pending drafts whose PROSPECT was not re-selected by today's re-run.

Why: rerun_pending.py re-ran research for every company in the queue, but
prospects.find() picked different people at ~20 of them, so the August drafts
to the ORIGINAL contacts (mostly CIOs/CTOs, all verified) were left untouched
with bodies that still cite August evidence. Withdrawing them throws away the
best contacts; approving them sends stale claims. So: rewrite them against the
company's newest research, keeping the same rep (parsed from the signature).

Skips any draft whose company has no research row from today - the writer
must not be re-run on stale evidence (indo-mim.com: site unreachable today).

    python3 tools/rewrite_untouched.py            # dry run
    python3 tools/rewrite_untouched.py --apply
"""
import json, sys
from datetime import date
sys.path.insert(0, "/opt/origami-outbound/src")
import write
from config import db

APPLY = "--apply" in sys.argv
TODAY = date.today()

with db() as conn, conn.cursor() as cur:
    cur.execute("SELECT full_name FROM reps WHERE active")
    reps = [r[0] for r in cur.fetchall()]
    cur.execute("""
        WITH today AS (SELECT min(xmin::text::bigint) x FROM research
                       WHERE created_at::date = current_date)
        SELECT e.id, c.domain, c.apollo_raw, p.first_name, p.title, e.body,
               r.raw, r.created_at::date
        FROM emails e
        JOIN prospects p ON p.id = e.prospect_id
        JOIN companies c ON c.id = p.company_id
        JOIN LATERAL (SELECT raw, created_at FROM research
                      WHERE company_id = c.id
                      ORDER BY created_at DESC, id DESC LIMIT 1) r ON true,
             today
        WHERE e.approved IS NULL AND e.xmin::text::bigint < today.x
        ORDER BY c.domain""")
    rows = cur.fetchall()

print(f"{len(rows)} untouched pending drafts")
done = skipped = 0
for eid, domain, org, first, title, body, raw, rdate in rows:
    rep = next((n for n in reps if n in body), None)
    if rdate != TODAY:
        print(f"  SKIP  {eid:>4} {domain:<26} research is {rdate}, not today")
        skipped += 1
        continue
    if rep is None:
        print(f"  SKIP  {eid:>4} {domain:<26} no rep signature found in body")
        skipped += 1
        continue
    verb = "WRITE" if APPLY else "would"
    print(f"  {verb} {eid:>4} {domain:<26} {first} / {title[:40]} / rep {rep}")
    if not APPLY:
        continue
    r = raw if isinstance(raw, dict) else json.loads(raw)
    org = org if isinstance(org, dict) else json.loads(org)
    e = write.write(org, r, first, title, {"full_name": rep})
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE emails SET subject=%s, body=%s, model=%s,
                       approved=NULL, approved_by=NULL, approved_at=NULL
                       WHERE id=%s""",
                    (e["subject"], e["body"], e.get("_model", "claude-fable-5"), eid))
    done += 1

print(f"\nrewritten {done}, skipped {skipped}")
print("Verify in the database, not from this line.")
