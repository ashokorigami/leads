"""Write the email for every prospect that already clears the send gate but has none.

This does NOT enrich, research or source. Those prospects are already qualified
and contact-verified; the only missing artefact is the draft. Running the full
pipeline over them would spend an Apollo credit and an Opus research call each,
and would append ANOTHER research row to companies that already have several -
which is the defect 016_sendable_latest_research.sql was written to contain.

Rows come from v_sendable, so domain, email AND name suppression are enforced by
the gate itself rather than re-implemented here. Research fields are taken from
the newest row with the same ordering the view uses.

Drafts are inserted with approved = NULL, so they land in /queue for review.
Nothing here can send.

    python3 tools/write_pending.py                # dry run, shows what it would do
    python3 tools/write_pending.py --limit 5 --apply
    python3 tools/write_pending.py --apply        # the rest

Run it from /opt/origami-outbound, never from /tmp - a stray /tmp/inspect.py
shadows the stdlib there (LESSONS.md sec.8).
"""
import sys

sys.path.insert(0, "/opt/origami-outbound/src")

from config import db
import write

APPLY = "--apply" in sys.argv
LIMIT = 0
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

SQL = """
SELECT v.prospect_id, v.score,
       p.first_name, p.title,
       c.name, c.employees, c.country, c.industry, c.domain,
       r.primary_trigger, r.angle, r.wedge, r.proof_ref
  FROM v_sendable v
  JOIN prospects p ON p.id = v.prospect_id
  JOIN companies c ON c.id = p.company_id
  JOIN LATERAL (
       SELECT rr.primary_trigger, rr.angle, rr.wedge, rr.proof_ref
         FROM research rr
        WHERE rr.company_id = c.id
        ORDER BY rr.created_at DESC, rr.id DESC
        LIMIT 1) r ON TRUE
 WHERE NOT EXISTS (SELECT 1 FROM emails e
                    WHERE e.prospect_id = v.prospect_id AND e.step = 1)
 ORDER BY v.score DESC, v.prospect_id
"""

with db() as c, c.cursor() as cur:
    cur.execute(SQL + (" LIMIT %s" % LIMIT if LIMIT else ""))
    rows = cur.fetchall()
    cur.execute("SELECT id, full_name FROM reps WHERE active ORDER BY id")
    reps = cur.fetchall()

if not reps:
    raise SystemExit("no active reps - refusing to write unsigned emails")

print(f"{len(rows)} prospect(s) clear the gate with no draft"
      + (f" (limited to {LIMIT})" if LIMIT else ""))
for pid, score, fn, title, cname, *_ in rows:
    rep = reps[pid % len(reps)][1]
    print(f"  prospect {pid:<5} score {score:<4} {(cname or '?')[:34]:<34} "
          f"-> {fn} ({(title or '?')[:28]})  rep: {rep}")

if not APPLY:
    print("\nDry run. Nothing written. Re-run with --apply.")
    raise SystemExit

print()
ok = failed = 0
for (pid, score, fn, title, cname, emp, country, ind, dom,
     trig, angle, wedge, proof) in rows:
    org = {"name": cname, "employees": emp, "country": country,
           "industry": ind, "domain": dom}
    r = {"primary_trigger": trig, "angle": angle,
         "wedge": wedge, "proof_ref": proof}
    rep = reps[pid % len(reps)][1]
    try:
        e = write.write(org, r, fn, title, {"full_name": rep})
    except Exception as ex:
        print(f"  prospect {pid} FAILED: {type(ex).__name__}: {ex}")
        failed += 1
        continue

    # write.write() already retries up to three times against this same gate and
    # raises rather than shipping. Re-asserting here costs nothing and means a
    # future change to write.py cannot quietly let an unobserved technology
    # through this path (LESSONS.md sec.1).
    still = write.unverified_tech(e["body"], str(trig or ""))
    if still:
        print(f"  prospect {pid} STILL NAMES UNVERIFIED TECH: {still} - not inserted")
        failed += 1
        continue

    with db() as c2, c2.cursor() as cur2:
        cur2.execute("""INSERT INTO emails (prospect_id, step, subject, body, model)
                        VALUES (%s, 1, %s, %s, %s)
                        ON CONFLICT (prospect_id, step) DO NOTHING""",
                     (pid, e["subject"], e["body"], e.get("_model", "claude-fable-5")))
        inserted = cur2.rowcount
    if inserted != 1:
        print(f"  prospect {pid} NOT INSERTED (conflict) - left alone")
        failed += 1
        continue
    print(f"  prospect {pid} written ({e.get('_rewrites', 0)} corrective pass"
          f"{'es' if e.get('_rewrites', 0) != 1 else ''})  rep: {rep}")
    ok += 1

print(f"\nwritten {ok}, failed {failed}")
print("Verify in the database, not from this line (LESSONS.md sec.5).")
