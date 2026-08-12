"""Find the buyer at qualified companies that have no prospect yet.

These companies already passed research and carry a score and a wedge; the only
missing artefact is a person. Re-running the full pipeline over them would spend
an Opus research call each AND append another research row to companies that
already have one - the defect 016_sendable_latest_research.sql exists to contain.

Credit cost is real: prospects.find() reveals at most 8 candidates per company
and stops as soon as it has `want` verified addresses. A company where nobody
advertises has_email costs nothing; a company where several candidates are
revealed and all fail the domain check costs up to 8.

A company where no verified contact is found is marked rejected with
"no verified contact found", exactly as pipeline.run_one() does. Without that,
every rerun would spend the same credits on the same hopeless companies again.

This inserts prospects only. It writes no drafts and cannot send - run
tools/write_pending.py afterwards to draft, which lands them in /queue.

    python3 tools/find_pending_people.py                 # dry run, no credits spent
    python3 tools/find_pending_people.py --limit 5 --apply
    python3 tools/find_pending_people.py --apply         # the rest

Run it from /opt/origami-outbound, never from /tmp (LESSONS.md sec.8).
"""
import sys

sys.path.insert(0, "/opt/origami-outbound/src")

from config import db
import prospects

APPLY = "--apply" in sys.argv
LIMIT = 0
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

# Newest research row per company, the same ordering the send gate uses, so this
# tool and v_sendable can never disagree about a company carrying several rows.
# The trigger and suppression clauses mirror v_sendable too: there is no point
# spending a credit on a company the gate would refuse to send to anyway.
SQL = """
SELECT c.id, c.domain, c.name, r.score, r.wedge
  FROM companies c
  JOIN LATERAL (
       SELECT rr.score, rr.wedge, rr.disqualify_reason
         FROM research rr
        WHERE rr.company_id = c.id
        ORDER BY rr.created_at DESC, rr.id DESC
        LIMIT 1) r ON TRUE
 WHERE c.stage::text = 'qualified'
   AND r.score >= 70
   AND r.disqualify_reason IS NULL
   AND NOT EXISTS (SELECT 1 FROM prospects p WHERE p.company_id = c.id)
   AND EXISTS (SELECT 1 FROM triggers t WHERE t.company_id = c.id
                 AND t.kind = ANY (ARRAY['hiring_eng','funding','exec_hire',
                       'weak_app','launch','headcount_growth','profile']))
   AND NOT EXISTS (SELECT 1 FROM suppression s
                    WHERE (s.kind='domain' AND s.value = c.domain)
                       OR (s.kind='name'   AND c.name ~* ('\\m' || s.value || '\\M')))
 ORDER BY r.score DESC, c.id
"""

with db() as c, c.cursor() as cur:
    cur.execute(SQL + (" LIMIT %s" % LIMIT if LIMIT else ""))
    rows = cur.fetchall()

print(f"{len(rows)} qualified company/companies with no prospect"
      + (f" (limited to {LIMIT})" if LIMIT else ""))

if not APPLY:
    for cid, dom, name, score, wedge in rows[:20]:
        label = (name or "?")[:34]
        print(f"  {cid:<6} score {score:<4} {label:<34} {wedge or '-':<17} {dom}")
    if len(rows) > 20:
        print(f"  ... and {len(rows) - 20} more")
    print("\nDry run. No Apollo credit spent. Re-run with --apply.")
    raise SystemExit

found = nocontact = failed = people_total = 0
for cid, dom, name, score, wedge in rows:
    try:
        people = prospects.find(dom, wedge, want=2)
    except Exception as ex:
        print(f"  {dom:<30} FAILED: {type(ex).__name__}: {ex}")
        failed += 1
        continue

    if not people:
        with db() as c2, c2.cursor() as cur2:
            cur2.execute("UPDATE companies SET stage='rejected', "
                         "rejected_reason='no verified contact found' WHERE id=%s",
                         (cid,))
        print(f"  {dom:<30} no verified contact - rejected")
        nocontact += 1
        continue

    with db() as c2, c2.cursor() as cur2:
        for per in people:
            cur2.execute("""INSERT INTO prospects (company_id, apollo_person_id,
                            first_name, last_name, title, seniority, email,
                            email_status, linkedin_url)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (company_id, email) DO UPDATE
                              SET title=EXCLUDED.title""",
                         (cid, per["apollo_person_id"], per["first_name"],
                          per["last_name"], per["title"], per["seniority"],
                          per["email"], per["email_status"], per["linkedin_url"]))
            people_total += 1
    who = ", ".join(f"{p['first_name']} ({(p['title'] or '?')[:24]})" for p in people)
    print(f"  {dom:<30} score {score:<4} -> {who}")
    found += 1

print(f"\ncompanies with contacts {found}, no contact {nocontact}, failed {failed}")
print(f"prospects inserted {people_total}")
print("Now run tools/write_pending.py to draft. Verify in the database, not from this line.")
