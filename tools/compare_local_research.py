"""Side-by-side: gpt-oss-120b (local, Blackwell) vs the newest stored Opus research.

READ-ONLY on the database: calls research.research() directly and never inserts.
Inputs are TODAY's (Apollo record, triggers and site pages refreshed by the
2026-10-28 morning run that died on the Anthropic 401), while the Opus verdict is
from its own run date - so a disagreement can be the model OR changed evidence.
The evidence column says which.

    OUTBOUND_LLM=local LOCAL_LLM_URL=http://127.0.0.1:18001/v1 \
        python3 tools/compare_local_research.py [n]
"""
import json, sys, time
sys.path.insert(0, "/opt/origami-outbound/src")
import company_profile, llm, research
from config import db, SCORE_THRESHOLD

assert llm.RESEARCH_CHAIN == ["local:gpt-oss-120b"], "set OUTBOUND_LLM=local"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5

with db() as conn, conn.cursor() as cur:
    cur.execute("""
        WITH fresh AS (SELECT DISTINCT company_id FROM triggers
                       WHERE created_at::date = current_date),
        opus AS (SELECT DISTINCT ON (company_id) company_id, score, wedge,
                        primary_trigger, disqualify_reason, created_at::date d
                 FROM research ORDER BY company_id, created_at DESC, id DESC)
        SELECT c.id, c.domain, c.apollo_raw, o.score, o.wedge, o.primary_trigger,
               o.disqualify_reason, o.d
        FROM companies c JOIN fresh f ON f.company_id = c.id
        JOIN opus o ON o.company_id = c.id
        ORDER BY (o.score >= %s) DESC, c.domain""", (SCORE_THRESHOLD,))
    rows = cur.fetchall()
    # mix: up to 3 that Opus passed, the rest that it failed
    passed = [r for r in rows if r[3] >= SCORE_THRESHOLD][:3]
    failed = [r for r in rows if r[3] < SCORE_THRESHOLD][:N - len(passed)]
    pick = (passed + failed + [r for r in rows if r not in passed + failed])[:N]
    trig = {}
    for r in pick:
        cur.execute("SELECT kind, detail FROM triggers WHERE company_id=%s", (r[0],))
        trig[r[0]] = [{"kind": k, "detail": d} for k, d in cur.fetchall()]

out = []
for cid, dom, org, oscore, owedge, otrig, odq, odate in pick:
    org = org if isinstance(org, dict) else json.loads(org)
    pages = company_profile.load(cid)
    t0 = time.time()
    try:
        r = research.research(org, trig[cid], pages)
        err = None
    except Exception as e:
        r, err = {}, f"{type(e).__name__}: {e}"
    sec = round(time.time() - t0, 1)
    row = {"domain": dom, "inputs": {"triggers": len(trig[cid]), "pages": len(pages)},
           "opus": {"date": str(odate), "score": oscore, "wedge": owedge,
                    "trigger": otrig, "disqualify": odq},
           "local": {"score": r.get("score"), "wedge": r.get("wedge"),
                     "trigger": r.get("primary_trigger"), "angle": r.get("angle"),
                     "disqualify": r.get("disqualify_reason"),
                     "evidence_quote": r.get("evidence_quote"),
                     "evidence_url": r.get("evidence_url"),
                     "quote_unverified": r.get("quote_unverified"),
                     "usage": r.get("_usage"), "sec": sec, "error": err}}
    out.append(row)
    ov = "PASS" if oscore >= SCORE_THRESHOLD else "fail"
    ls = r.get("score")
    lv = "ERR " if err else ("PASS" if (ls or 0) >= SCORE_THRESHOLD and not r.get("disqualify_reason") else "fail")
    print(f"{dom:<26} opus {ov} {oscore:>3} ({odate})  local {lv} {ls}  {sec}s")

path = "/opt/origami-outbound/logs/compare-local-2026-10-28-n" + str(N) + ".json"
json.dump(out, open(path + ".tmp", "w"), indent=2, default=str)
import os; os.replace(path + ".tmp", path)
assert len(out) == len(pick), "loop dropped a company"
print(f"\n{len(out)} compared -> {path}")
