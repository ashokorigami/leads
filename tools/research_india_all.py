"""Research every Indian company in the pool, writing results to the database.

Resumable: skips anything that already has a research row, so it can be killed
and restarted without losing or repeating work.

No Apollo enrichment - that costs a credit each and we already have name,
domain and segment from search. Evidence comes from the company's own site, and
the quote is verified against the stored text before it can become an opening
fact.

Segments are worked in conversion order: insurance and engineering first,
because those are the measured best performers.
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/opt/origami-outbound/src")

import company_profile
import research
from config import db

# Best-converting first. Anything not listed is worked last.
PRIORITY = ["insurance", "engineering", "construction", "pharma_med",
            "utilities", "manufacturing", "freight", "warehousing",
            "food_mfg", "distribution", "wholesale", "retail", "legal",
            "healthcare"]

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0
lock = threading.Lock()
counts = {"done": 0, "qualified": 0, "rejected": 0, "nosite": 0, "error": 0,
          "in_tok": 0, "out_tok": 0}


def todo() -> list[dict]:
    order = " ".join(f"WHEN '{s}' THEN {i}" for i, s in enumerate(PRIORITY))
    with db() as c, c.cursor() as cur:
        cur.execute(f"""
            SELECT c.id, c.name, c.domain, c.segment, c.employees, c.industry
            FROM companies c
            WHERE c.country = 'India'
              AND NOT EXISTS (SELECT 1 FROM research r WHERE r.company_id = c.id)
            ORDER BY CASE c.segment {order} ELSE 99 END, c.name""")
        cols = ["id", "name", "domain", "segment", "employees", "industry"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def persist(co, r, pages):
    with db() as c, c.cursor() as cur:
        cur.execute("""INSERT INTO research (company_id,model,score,wedge,
                       primary_trigger,angle,proof_ref,disqualify_reason,raw,
                       input_tokens,output_tokens)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (co["id"], r.get("_model", "claude-opus-5"), r["score"],
                     None if r["wedge"] == "none" else r["wedge"],
                     r["primary_trigger"], r["angle"], r["proof_ref"],
                     r.get("disqualify_reason"), json.dumps(r),
                     r.get("_usage", {}).get("in", 0),
                     r.get("_usage", {}).get("out", 0)))
        # A verified quote is a first-class trigger - it is what lets a company
        # with no job advert qualify at all.
        if r.get("evidence_quote") and r.get("evidence_url"):
            cur.execute("""INSERT INTO triggers (company_id,kind,detail,
                           evidence_url,observed_at,source)
                           VALUES (%s,'profile',%s,%s,now(),'website')""",
                        (co["id"], r["evidence_quote"][:500], r["evidence_url"]))
        good = (r["score"] or 0) >= 70 and not r.get("disqualify_reason")
        cur.execute("""UPDATE companies SET stage=%s, rejected_reason=%s,
                       updated_at=now() WHERE id=%s""",
                    ("qualified" if good else "rejected",
                     None if good else (r.get("disqualify_reason")
                                        or f"score {r['score']}"),
                     co["id"]))
        return good


def one(co):
    try:
        pages = company_profile.fetch(co["domain"], max_pages=3)
        if not pages:
            with db() as c, c.cursor() as cur:
                cur.execute("UPDATE companies SET stage='rejected', "
                            "rejected_reason=%s, updated_at=now() WHERE id=%s",
                            ("site unreachable - no evidence to research",
                             co["id"]))
            with lock:
                counts["nosite"] += 1; counts["done"] += 1
            return
        org = {"name": co["name"], "primary_domain": co["domain"],
               "country": "India", "industry": co["industry"] or co["segment"],
               "estimated_num_employees": co["employees"]}
        r = research.research(org, [], pages)
        good = persist(co, r, pages)
        with lock:
            counts["done"] += 1
            counts["qualified" if good else "rejected"] += 1
            counts["in_tok"] += r.get("_usage", {}).get("in", 0)
            counts["out_tok"] += r.get("_usage", {}).get("out", 0)
    except Exception as ex:
        with lock:
            counts["error"] += 1; counts["done"] += 1
        print(f"    ERR {co['name'][:34]}: {type(ex).__name__}: {ex}"[:150],
              flush=True)


if __name__ == "__main__":
    work = todo()
    if LIMIT:
        work = work[:LIMIT]
    print(f"to research: {len(work)} Indian companies", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(one, co) for co in work]
        for _ in as_completed(futs):
            d = counts["done"]
            if d % 25 == 0:
                el = time.time() - t0
                rate = d / el if el else 0
                cost = counts["in_tok"] / 1e6 * 5 + counts["out_tok"] / 1e6 * 25
                print(f"  [{d}/{len(work)}] qualified {counts['qualified']} | "
                      f"rejected {counts['rejected']} | no-site {counts['nosite']} | "
                      f"err {counts['error']} | ${cost:.2f} | "
                      f"{rate*3600:.0f}/hr", flush=True)
    cost = counts["in_tok"] / 1e6 * 5 + counts["out_tok"] / 1e6 * 25
    print(f"\nFINISHED {counts['done']} in {(time.time()-t0)/60:.0f} min")
    print(f"  qualified {counts['qualified']} | rejected {counts['rejected']} | "
          f"no site {counts['nosite']} | errors {counts['error']}")
    print(f"  approx LLM cost ${cost:.2f}")
