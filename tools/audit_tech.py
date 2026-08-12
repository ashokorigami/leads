"""Read-only audit: does any draft name a technology we never observed?

Runs write.unverified_tech() over every email, using ONLY primary_trigger as the
evidence set - the single field built from real Apollo job data. `angle` and
`proof_ref` are model output and must never count as evidence (LESSONS.md sec.1).

This script performs no writes of any kind. It opens the database read-only and
has no UPDATE, INSERT or DELETE path.

    python3 tools/audit_tech.py
"""
import sys

sys.path.insert(0, "/opt/origami-outbound/src")

from config import db
import write

with db() as c, c.cursor() as cur:
    # DISTINCT ON: a company can carry several research rows; joining them all
    # made one email appear three times in an earlier audit.
    cur.execute("""
        SELECT DISTINCT ON (e.id)
               e.id, e.approved, c.name, r.primary_trigger, e.body
          FROM emails e
          JOIN prospects p ON p.id = e.prospect_id
          JOIN companies c ON c.id = p.company_id
          JOIN research  r ON r.company_id = c.id
         ORDER BY e.id, r.created_at DESC, r.id DESC""")
    rows = cur.fetchall()

bad = []
for eid, approved, cname, trig, body in rows:
    hit = write.unverified_tech(body or "", str(trig or ""))
    if hit:
        bad.append((eid, approved, cname, hit))

print(f"audited {len(rows)} drafts")
if not bad:
    print("clean: no draft names a technology outside its observed trigger")
else:
    print(f"{len(bad)} FLAGGED:")
    for eid, approved, cname, hit in bad:
        state = "APPROVED" if approved else "pending"
        print(f"  #{eid:<4} {state:<9} {(cname or '?')[:34]:<34} {hit}")
