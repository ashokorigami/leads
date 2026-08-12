"""Run the full pipeline over a metered batch of staged companies, one country.

This is the EXPENSIVE half: per company it spends an Apollo enrichment credit,
an Opus research call, then people-search and reveal credits, then a Fable write.
source_us.py stages for free; this is what costs money, so it takes an explicit
--limit and defaults to a small one.

Country matters because `stage='sourced'` currently holds both the staged US
batch and older rows from other regions; source.pending() would mix them.

    python3 tools/run_batch.py --limit 15
    python3 tools/run_batch.py --limit 100 --country "United States"
"""
import sys
from collections import Counter

sys.path.insert(0, "/opt/origami-outbound/src")

import pipeline
from config import db

LIMIT = 15
COUNTRY = "United States"
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])
if "--country" in sys.argv:
    COUNTRY = sys.argv[sys.argv.index("--country") + 1]

with db() as c, c.cursor() as cur:
    cur.execute("""SELECT domain FROM companies
                    WHERE stage::text = 'sourced' AND country = %s
                      AND NOT EXISTS (SELECT 1 FROM suppression s
                                       WHERE s.kind='domain' AND s.value = companies.domain)
                    ORDER BY employees DESC NULLS LAST
                    LIMIT %s""", (COUNTRY, LIMIT))
    domains = [r[0] for r in cur.fetchall()]

print(f"{len(domains)} {COUNTRY} company/companies queued for the full pipeline")
if not domains:
    raise SystemExit

tally = pipeline.run(domains)

print("\noutcome tally:")
for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
    print(f"  {v:>4}  {k}")

buckets = Counter()
for k, v in tally.items():
    head = k.split("_")[0]
    buckets["queued" if head == "queued" else head] += v
print("\nsummary:")
for k, v in buckets.most_common():
    print(f"  {k:<12} {v}")
print("\nVerify in the database, not from this line.")
