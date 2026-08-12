"""End-to-end run: source -> enrich -> trigger -> research -> write -> persist.

Cheapest filter first. A company that fails an early stage never reaches the
expensive one, so Opus is only ever spent on companies that already have a
nameable fact attached.
"""
import json, sys
import psycopg
from config import db, SCORE_THRESHOLD
import apollo, triggers, research, write, prospects, appstore
import company_profile

QUALIFYING = ('hiring_eng','funding','exec_hire','weak_app','launch','headcount_growth')


def suppressed(cur, domain: str, name: str | None = None) -> bool:
    """Domain match, plus whole-word NAME match.

    Domain-only suppression missed sterlitecopper.com on 2026-08-02 and the NDA
    client's own subsidiary was researched, scored 74, and reached a published
    target list. Listing subsidiary domains one at a time will always miss the
    next one.

    The name match uses \\m..\\M word boundaries so 'Bhaktivedanta Hospital', an
    unrelated Mumbai hospital, is NOT suppressed. Substring matching on names is
    a recurring bug here - it caught me again in the very check written to find
    this leak.
    """
    cur.execute("SELECT 1 FROM suppression WHERE kind='domain' AND value=%s",
                (domain,))
    if cur.fetchone():
        return True
    if not name:
        return False
    cur.execute("""SELECT 1 FROM suppression
                   WHERE kind='name' AND %s ~* ('\\m' || value || '\\M')""",
                (name,))
    return cur.fetchone() is not None


def run_one(cur, domain: str, verbose=True) -> str:
    """Returns the stage at which this company stopped."""
    domain = domain.lower().strip()

    cur.execute("SELECT name FROM companies WHERE domain=%s", (domain,))
    _row = cur.fetchone()
    if suppressed(cur, domain, _row[0] if _row else None):
        return "suppressed"

    # Cheap pre-screen. Enrichment costs a credit; job postings do not, and the
    # org id already came back free from search. Batch 4 enriched 25 companies to
    # discover 17 had no trigger - that is 17 wasted credits per 25. So if we
    # already know the org id, check for engineering postings FIRST and only pay
    # to enrich companies that have one.
    with_id = None
    cur.execute("SELECT apollo_org_id FROM companies WHERE domain=%s", (domain,))
    row = cur.fetchone()
    if row and row[0]:
        with_id = row[0]
        try:
            posts = apollo.job_postings(with_id)
            # A hiring signal is now a BONUS, not a requirement. It used to
            # short-circuit here, and it was rejecting 142 companies against 7
            # rejected for genuinely poor fit - it measured Apollo's job-board
            # coverage, not whether the company needed us.
            _ = triggers.from_jobs(posts)
        except Exception:
            pass                       # best effort, never fatal

    org = apollo.enrich(domain)
    if not org:
        return "no_apollo_record"

    cur.execute("""
        INSERT INTO companies (apollo_org_id, domain, name, industry, employees,
                               country, founded_year, linkedin_url, stage,
                               enriched_at, apollo_raw)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'enriched',now(),%s)
        ON CONFLICT (domain) DO UPDATE SET
          apollo_raw=EXCLUDED.apollo_raw, enriched_at=now(), stage='enriched',
          employees=COALESCE(EXCLUDED.employees, companies.employees),
          name=COALESCE(EXCLUDED.name, companies.name),
          industry=COALESCE(EXCLUDED.industry, companies.industry),
          country=COALESCE(EXCLUDED.country, companies.country)
        RETURNING id""",
        (org.get("id"), domain, org.get("name"), org.get("industry"),
         org.get("estimated_num_employees"), org.get("country"),
         org.get("founded_year"), org.get("linkedin_url"), json.dumps(org)))
    cid = cur.fetchone()[0]

    tg = triggers.extract(org, apollo.job_postings(org["id"]))
    try:
        tg += appstore.triggers_for(org.get("name") or domain, domain,
                                    org.get("estimated_num_employees"),
                                    org.get("country"))
    except Exception:
        pass                      # app store is best-effort, never fatal
    cur.execute("DELETE FROM triggers WHERE company_id=%s", (cid,))
    for t in tg:
        cur.execute("""INSERT INTO triggers (company_id,kind,detail,evidence_url,
                       observed_at,source) VALUES (%s,%s,%s,%s,%s,%s)""",
                    (cid, t["kind"], t["detail"], t.get("evidence_url"),
                     t.get("observed_at") or None, t["source"]))

    # What the company says about itself. Free, global, and the only evidence
    # available in markets Apollo cannot see. Stored so the researcher can quote
    # only what was actually fetched.
    try:
        pages = company_profile.fetch(domain)
        company_profile.store(cid, pages)
    except Exception:
        pages = []                     # best effort, never fatal

    if not tg and not pages:
        cur.execute("UPDATE companies SET stage='rejected', rejected_reason=%s WHERE id=%s",
                    ("no signal and site unreachable - nothing to research", cid))
        return "no_evidence"

    r = research.research(org, tg, pages)

    # A verified quote becomes a first-class trigger, so companies with no job
    # advert can still qualify - on a fact they published themselves.
    if r.get("evidence_quote") and r.get("evidence_url"):
        cur.execute("""INSERT INTO triggers (company_id,kind,detail,evidence_url,
                       observed_at,source) VALUES (%s,'profile',%s,%s,now(),'website')""",
                    (cid, r["evidence_quote"][:500], r["evidence_url"]))
    cur.execute("""INSERT INTO research (company_id,model,score,wedge,primary_trigger,
                   angle,proof_ref,disqualify_reason,raw,input_tokens,output_tokens)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (cid, r.get("_model", "claude-opus-5"), r["score"],
                 None if r["wedge"] == "none" else r["wedge"],
                 r["primary_trigger"], r["angle"], r["proof_ref"],
                 r["disqualify_reason"], json.dumps(r),
                 r["_usage"]["in"], r["_usage"]["out"]))

    if r["score"] < SCORE_THRESHOLD or r["disqualify_reason"]:
        cur.execute("UPDATE companies SET stage='rejected', rejected_reason=%s WHERE id=%s",
                    (r["disqualify_reason"] or f"score {r['score']}", cid))
        return f"rejected_{r['score']}"

    cur.execute("UPDATE companies SET stage='qualified' WHERE id=%s", (cid,))

    people = prospects.find(domain, r["wedge"], want=2)
    if not people:
        cur.execute("UPDATE companies SET stage='rejected', rejected_reason=%s WHERE id=%s",
                    ("no verified contact found", cid))
        return f"no_contact_{r['score']}"

    # round-robin the reps so load spreads evenly
    cur.execute("SELECT id, full_name FROM reps WHERE active ORDER BY id")
    reps = cur.fetchall()

    written = 0
    for i, per in enumerate(people):
        cur.execute("""INSERT INTO prospects (company_id, apollo_person_id, first_name,
                       last_name, title, seniority, email, email_status, linkedin_url)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (company_id, email) DO UPDATE SET title=EXCLUDED.title
                       RETURNING id""",
                    (cid, per["apollo_person_id"], per["first_name"], per["last_name"],
                     per["title"], per["seniority"], per["email"],
                     per["email_status"], per["linkedin_url"]))
        pid = cur.fetchone()[0]

        rep = reps[(pid + i) % len(reps)]
        e = write.write(org, r, per["first_name"], per["title"],
                        {"full_name": rep[1]})
        cur.execute("""INSERT INTO emails (prospect_id, step, subject, body, model)
                       VALUES (%s,1,%s,%s,%s)
                       ON CONFLICT (prospect_id, step) DO UPDATE SET
                         subject=EXCLUDED.subject, body=EXCLUDED.body,
                         -- Approval attaches to the TEXT, not to the row. A
                         -- rewrite that kept approved=TRUE would send a body no
                         -- human ever read, so a rewritten draft goes back into
                         -- the queue for a fresh decision.
                         approved=NULL, approved_by=NULL, approved_at=NULL""",
                    (pid, e["subject"], e["body"], e.get("_model", "claude-fable-5")))
        written += 1

    cur.execute("UPDATE companies SET stage='queued' WHERE id=%s", (cid,))
    return f"queued_{r['score']}_{written}emails"


def run(domains: list[str]):
    tally = {}
    with db() as conn, conn.cursor() as cur:
        for d in domains:
            try:
                outcome = run_one(cur, d)
            except Exception as e:
                # Put it back in the queue. A provider incident should cost us a
                # retry, not a prospect - errored companies were previously left
                # stranded mid-pipeline where pending() could never see them.
                cur.execute("""UPDATE companies SET stage='sourced',
                               rejected_reason=%s WHERE domain=%s""",
                            (f"retry after: {type(e).__name__}", d))
                outcome = f"error: {type(e).__name__} (requeued)"
            tally[outcome] = tally.get(outcome, 0) + 1
            print(f"  {d:<28} {outcome}")
    return tally


if __name__ == "__main__":
    run([d.strip() for d in sys.argv[1:] if d.strip()])
