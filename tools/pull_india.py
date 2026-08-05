"""Pull the full Indian universe from Apollo into `companies`, with segment and
country recorded, then cross-reference the NSE listed universe.

Search is free - only enrichment costs a credit - so this builds the target list
at no cost. Domains come back with the search, which is what NSE cannot give us.
"""
import csv
import io
import json
import re
import sys

import httpx

sys.path.insert(0, "/opt/origami-outbound/src")
import source
from config import db

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 Chrome/126.0 Safari/537.36")}

print("=== 1. Apollo India, all doc-heavy segments ===")
staged = 0
per_seg = {}
for seg in source.SEGMENTS:
    try:
        rows = source.candidates(seg, country="India", pages=40, per_page=25)
    except Exception as e:
        print(f"  {seg:16} ERR {type(e).__name__}")
        continue
    n = source.stage(rows)
    per_seg[seg] = len(rows)
    staged += n
    print(f"  {seg:16} fetched {len(rows):>4}   staged/updated {n:>4}")

print(f"\ntotal fetched from Apollo: {sum(per_seg.values())}")

print("\n=== 2. NSE listed universe (authoritative, for cross-reference) ===")
full = list(csv.DictReader(io.StringIO(httpx.get(
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
    headers=UA, timeout=60).text)))
tot = list(csv.DictReader(io.StringIO(httpx.get(
    "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
    headers=UA, timeout=60).text)))
print(f"  NSE listed companies      : {len(full)}")
print(f"  with industry classification: {len(tot)}")

def norm(s):
    s = re.sub(r"\s*(Ltd\.?|Limited|Private|Pvt\.?)\s*", " ", s or "", flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())

nse_by_norm = {norm(r["NAME OF COMPANY"]): r["NAME OF COMPANY"].strip()
               for r in full}

print("\n=== 3. What is now in the database for India ===")
with db() as c, c.cursor() as cur:
    cur.execute("SELECT count(*) FROM companies WHERE country='India'")
    india = cur.fetchone()[0]
    cur.execute("""SELECT segment, count(*) FROM companies
                   WHERE country='India' GROUP BY segment ORDER BY 2 DESC""")
    by_seg = cur.fetchall()
    cur.execute("SELECT name FROM companies WHERE country='India'")
    names = [r[0] for r in cur.fetchall()]

listed_hits = sum(1 for n in names if norm(n) in nse_by_norm)
print(f"  Indian companies in DB    : {india}")
for s, n in by_seg:
    print(f"     {(s or 'unclassified'):16} {n}")
print(f"\n  of those, matched to an NSE-listed name: {listed_hits}")
print(f"  (the rest are unlisted, private, or MNC subsidiaries - still valid targets)")

json.dump({"apollo_by_segment": per_seg, "nse_listed": len(full),
           "nse_classified": len(tot), "india_in_db": india,
           "matched_nse": listed_hits},
          open("/opt/origami-outbound/india_universe.json", "w"), indent=2)
