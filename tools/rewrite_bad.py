"""Rewrite every email that names a technology we never observed.

Keeps the SAME rep (parsed from the existing signature) so nothing about who is
writing changes - only the false claim goes. Any email that was already
approved is reset to pending, because Ashok approved a version that no longer
exists and must see the new one.
"""
import re
import sys
sys.path.insert(0, "/opt/origami-outbound/src")

from config import db
import write

DRY = "--apply" not in sys.argv

with db() as c, c.cursor() as cur:
    # DISTINCT ON: a company can have several research rows, and joining them
    # all made one email appear three times in the first run of this audit.
    cur.execute("""
        SELECT DISTINCT ON (e.id)
               e.id, e.approved, e.body,
               p.first_name, p.title,
               c.name, c.employees, c.country, c.industry, c.domain,
               r.primary_trigger, r.angle, r.wedge, r.proof_ref
        FROM emails e
        JOIN prospects p ON p.id = e.prospect_id
        JOIN companies c ON c.id = p.company_id
        JOIN research  r ON r.company_id = c.id
        ORDER BY e.id, r.created_at DESC""")
    rows = cur.fetchall()
    cur.execute("SELECT full_name FROM reps WHERE active")
    rep_names = [x[0] for x in cur.fetchall()]

def scrub_angle(angle: str, trig: str) -> str:
    """Remove invented technology from the SCORER's angle before re-writing.

    The angle is an instruction to the writer. Leaving "deploys inside
    Boskalis' own Azure tenancy" in it means telling the writer to make the
    claim and then rejecting it three times. Deleting the token leaves
    "Boskalis' own tenancy", which is both true and still reads.
    """
    for name in write.unverified_tech(angle, trig):
        angle = re.sub(rf"\s*\b{re.escape(name)}\b", "", angle, flags=re.I)
    return re.sub(r"\s{2,}", " ", angle).strip()


todo = []
for (eid, appr, body, fn, title, cname, emp, country, ind, dom,
     trig, angle, wedge, proof) in rows:
    # OBSERVED only. `angle` is model output - the very field that invented Azure.
    evidence = str(trig or "")
    bad = write.unverified_tech(body, evidence)
    if bad:
        rep = next((rn for rn in rep_names if rn in (body or "")), rep_names[0])
        todo.append((eid, appr, bad, rep, fn, title,
                     {"name": cname, "employees": emp, "country": country,
                      "industry": ind, "domain": dom},
                     {"primary_trigger": trig,
                      "angle": scrub_angle(angle or "", trig or ""),
                      "wedge": wedge, "proof_ref": proof}))

print(f"{len(todo)} of {len(rows)} emails name unverified technology")
for eid, appr, bad, rep, *_ in todo:
    state = "APPROVED" if appr else "pending"
    print(f"  #{eid:<4} {state:<9} {bad}  (rep: {rep})")

if DRY:
    print("\nDry run. Re-run with --apply to rewrite.")
    raise SystemExit

print()
ok = failed = 0
for eid, appr, bad, rep, fn, title, org, r in todo:
    try:
        e = write.write(org, r, fn, title, {"full_name": rep})
    except Exception as ex:
        print(f"  #{eid} FAILED: {ex}")
        failed += 1
        continue
    still = write.unverified_tech(e["body"], str(r.get("primary_trigger") or ""))
    if still:
        print(f"  #{eid} STILL BAD after rewrite: {still} - left untouched")
        failed += 1
        continue
    with db() as c, c.cursor() as cur:
        cur.execute("""UPDATE emails
                       SET subject=%s, body=%s, model=%s,
                           approved=NULL, approved_by=NULL, approved_at=NULL
                       WHERE id=%s""",
                    (e["subject"], e["body"], e.get("_model"), eid))
    print(f"  #{eid} rewritten ({e.get('_rewrites', 0)} corrective pass"
          f"{'es' if e.get('_rewrites', 0) != 1 else ''})"
          + ("  [was approved -> back to pending]" if appr else ""))
    ok += 1

print(f"\nrewritten {ok}, failed {failed}")
