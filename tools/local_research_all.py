"""gpt-oss-120b research over every company with a draft in the queue - VERDICTS NOT STORED.

Refreshes the INPUTS exactly as pipeline.run_one does (Apollo enrich, job-posting and
app-store triggers, website pages -> companies / triggers / company_sources), then runs
research.research() on the local model and writes the verdicts to a JSON file only.

Deliberately does NOT insert into `research`: v_sendable joins the NEWEST research row,
so a stored local "fail" would silently make that company's drafts unsendable - a
withdrawal by another name. Operator asked for withdrawals off (2026-10-28).

    OUTBOUND_LLM=local LOCAL_LLM_URL=http://127.0.0.1:18001/v1 \
        python3 -u tools/local_research_all.py
"""
import json, os, sys, time
sys.path.insert(0, "/opt/origami-outbound/src")
import apollo, appstore, company_profile, llm, research, triggers
from config import db, SCORE_THRESHOLD

assert llm.RESEARCH_CHAIN == ["local:gpt-oss-120b"], "set OUTBOUND_LLM=local"
OUT = "/opt/origami-outbound/logs/local-research-2026-10-28.json"

with db() as conn, conn.cursor() as cur:
    cur.execute("""
        SELECT c.id, c.domain, count(e.id)
        FROM emails e JOIN prospects p ON p.id = e.prospect_id
        JOIN companies c ON c.id = p.company_id
        WHERE e.approved IS NULL GROUP BY c.id, c.domain ORDER BY c.domain""")
    companies = cur.fetchall()
print(f"{len(companies)} companies behind pending drafts", flush=True)

results = []
for cid, dom, ndrafts in companies:
    t0 = time.time()
    row = {"domain": dom, "drafts": ndrafts}
    try:
        org = apollo.enrich(dom)
        if not org:
            raise RuntimeError("no Apollo record")
        tg = triggers.extract(org, apollo.job_postings(org["id"]))
        try:
            tg += appstore.triggers_for(org.get("name") or dom, dom,
                                        org.get("estimated_num_employees"), org.get("country"))
        except Exception:
            pass
        try:
            pages = company_profile.fetch(dom)
        except Exception:
            pages = []
        with db() as conn, conn.cursor() as cur:
            cur.execute("UPDATE companies SET apollo_raw=%s, enriched_at=now() WHERE id=%s",
                        (json.dumps(org), cid))
            cur.execute("DELETE FROM triggers WHERE company_id=%s", (cid,))
            for t in tg:
                cur.execute("""INSERT INTO triggers (company_id,kind,detail,evidence_url,
                               observed_at,source) VALUES (%s,%s,%s,%s,%s,%s)""",
                            (cid, t["kind"], t["detail"], t.get("evidence_url"),
                             t.get("observed_at") or None, t["source"]))
        if pages:
            company_profile.store(cid, pages)
        row["inputs"] = {"triggers": [f"[{t['kind']}] {t['detail']}" for t in tg],
                         "pages": len(pages)}
        if not tg and not pages:
            row["verdict"] = "no_evidence"
        else:
            r = research.research(org, tg, pages)
            ok = (r.get("score") or 0) >= SCORE_THRESHOLD and not r.get("disqualify_reason")
            row["verdict"] = "PASS" if ok else "fail"
            row["local"] = {k: r.get(k) for k in (
                "score", "wedge", "primary_trigger", "angle", "proof_ref",
                "disqualify_reason", "evidence_quote", "evidence_url", "quote_unverified", "_usage")}
    except Exception as e:
        row["verdict"] = "error"
        row["error"] = f"{type(e).__name__}: {e}"[:300]
    row["sec"] = round(time.time() - t0, 1)
    results.append(row)
    sc = (row.get("local") or {}).get("score")
    print(f"{len(results):>3}/{len(companies)} {dom:<28} {row['verdict']:<11} {sc!s:>4}  "
          f"drafts {ndrafts}  {row['sec']}s", flush=True)
    json.dump(results, open(OUT + ".tmp", "w"), indent=2, default=str)
    os.replace(OUT + ".tmp", OUT)

assert len(results) == len(companies), "loop dropped a company"
tally = {}
for r in results:
    tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
print("\ntally:", tally, "->", OUT, flush=True)
print("DONE", flush=True)
