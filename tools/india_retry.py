"""Retry only the companies whose site fetch failed, now that fetch() falls
back to the www host. Merges into the existing result file."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/opt/origami-outbound/src")
sys.path.insert(0, "/opt/origami-outbound/tools")
from india_research import one, CANDIDATES

PATH = "/opt/origami-outbound/india_targets.json"
done = json.load(open(PATH))
by_domain = {r["domain"]: r for r in done}

retry = [c for c in CANDIDATES if by_domain.get(c[0], {}).get("error")]
print(f"retrying {len(retry)} that failed to fetch\n")

recovered = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(one, c): c for c in retry}
    for i, f in enumerate(as_completed(futs), 1):
        r = f.result()
        if not r["error"]:
            recovered += 1
        by_domain[r["domain"]] = r
        flag = r["error"] or (f"score {r['score']}" +
                              ("" if r["url"] else "  [QUOTE UNVERIFIED]"))
        print(f"[{i}/{len(retry)}] {r['name'][:38]:40} {flag}", flush=True)

out = sorted(by_domain.values(), key=lambda r: -(r["score"] or 0))
json.dump(out, open(PATH, "w"), indent=2)
ok = [r for r in out if r["score"]]
print(f"\nrecovered {recovered} of {len(retry)}")
print(f"TOTAL researched {len(ok)} of {len(CANDIDATES)}; "
      f"{sum(1 for r in ok if (r['score'] or 0) >= 70)} score 70+; "
      f"{sum(1 for r in ok if r['url'])} with a VERIFIED quote")
