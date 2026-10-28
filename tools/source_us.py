"""Source US companies, driven by the `segments` table rather than a hardcoded list.

source.py carries its own SEGMENTS dict and a flat SIZES list. The `segments`
table carries the same NAICS plus min_employees, max_employees, priority and the
offer each segment maps to - and it is what /territory and the plan render. Two
lists of segments drift; this reads the one the rest of the system reads.

Sourcing is the CHEAP half: mixed_companies/search plus an INSERT. No enrichment
credit is spent here and no research call is made. The expensive half is
pipeline.run_one(), which enriches and runs Opus per company - run that
separately, in metered batches, against what this stages.

Apollo's org search returns NO location field at all, so the country we filter
on is the only truthful source for where a company is; it is recorded as such.

    python3 tools/source_us.py                     # dry run, stages nothing
    python3 tools/source_us.py --apply             # priority 1 segments
    python3 tools/source_us.py --apply --priority 2
    python3 tools/source_us.py --apply --segment engineering --pages 6
    python3 tools/source_us.py --country "South Africa" --priority 2
"""
import sys

sys.path.insert(0, "/opt/origami-outbound/src")

import apollo
import source
from config import db

COUNTRY = "United States"
if "--country" in sys.argv:
    COUNTRY = sys.argv[sys.argv.index("--country") + 1]

APPLY = "--apply" in sys.argv
PAGES = 4
MAXPRI = 1
ONLY = None
if "--pages" in sys.argv:
    PAGES = int(sys.argv[sys.argv.index("--pages") + 1])
if "--priority" in sys.argv:
    MAXPRI = int(sys.argv[sys.argv.index("--priority") + 1])
if "--segment" in sys.argv:
    ONLY = sys.argv[sys.argv.index("--segment") + 1]

with db() as c, c.cursor() as cur:
    cur.execute("""SELECT code, name, naics, min_employees, max_employees, priority
                     FROM segments
                    WHERE priority <= %s AND (%s::text IS NULL OR code = %s::text)
                    ORDER BY priority, code""", (MAXPRI, ONLY, ONLY))
    segs = cur.fetchall()

if not segs:
    raise SystemExit("no segment matched - check --segment / --priority")

print(f"{COUNTRY} - {len(segs)} segment(s), {PAGES} pages each"
      + ("" if APPLY else "   [DRY RUN]"))

# Apollo wants employee ranges as "min,max" strings. The table's open-ended
# max becomes a large ceiling rather than being dropped, which would have
# silently excluded exactly the biggest, most document-heavy targets.
def ranges(lo, hi):
    lo = lo or 200
    hi = hi or 100000
    bands = [(lo, 1000), (1001, 5000), (5001, 10000), (10001, hi)]
    return [f"{a},{b}" for a, b in bands if a <= hi and b >= lo and a < b]

total_found = total_staged = 0
for code, name, naics, lo, hi, pri in segs:
    found = []
    seen = set()
    for page in range(1, PAGES + 1):
        try:
            d = apollo.search_companies(
                page=page, per_page=25,
                organization_num_employees_ranges=ranges(lo, hi),
                organization_naics_codes=[str(n) for n in naics],
                organization_locations=[COUNTRY])
        except Exception as ex:
            print(f"  {code:<14} page {page} FAILED: {type(ex).__name__}: {ex}")
            break
        orgs = d.get("organizations") or d.get("accounts") or []
        if not orgs:
            break
        for o in orgs:
            dom = (o.get("primary_domain") or "").lower().strip()
            if not dom or dom in seen:
                continue
            seen.add(dom)
            found.append({
                "domain": dom,
                "apollo_org_id": o.get("id"),
                "name": o.get("name"),
                "employees": o.get("estimated_num_employees"),
                "country": COUNTRY,     # the filter is the only truthful source
                "segment": code,
            })

    staged = source.stage(found) if APPLY else 0
    total_found += len(found)
    total_staged += staged
    print(f"  p{pri} {code:<14} {name[:30]:<30} found {len(found):>4}"
          + (f"   newly staged {staged:>4}" if APPLY else ""))

print(f"\nfound {total_found}"
      + (f", newly staged {total_staged}" if APPLY else " (nothing staged)"))
if not APPLY:
    print("Dry run. Re-run with --apply.")
else:
    print("Staged as 'sourced'. Enrichment and research have NOT run and are "
          "where the credits go - run pipeline.run() in metered batches next.")
