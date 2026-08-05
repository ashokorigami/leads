"""How many Indian companies can Apollo give us WITH a domain, at our size bar?

Domains are the bottleneck: NSE publishes no websites, Wikidata covers 11% with
false matches on generic names, name-guessing produced garbage (ask.com for ASK
Automotive), and DuckDuckGo blocks programmatic use. Apollo's search returns
primary_domain for free - if the volume is there, that is the route.
"""
import sys
sys.path.insert(0, "/opt/origami-outbound/src")
import apollo
import source

total = 0
for seg, naics in source.SEGMENTS.items():
    try:
        d = apollo.search_companies(
            page=1, per_page=25,
            organization_num_employees_ranges=source.SIZES,
            organization_naics_codes=naics,
            organization_locations=["India"])
    except Exception as e:
        print(f"  {seg:16} ERR {type(e).__name__}")
        continue
    p = d.get("pagination") or {}
    orgs = d.get("organizations") or d.get("accounts") or []
    n = p.get("total_entries", 0)
    dom = sum(1 for o in orgs if o.get("primary_domain"))
    total += n
    print(f"  {seg:16} total={n:>6}   page-1 with domain {dom}/{len(orgs)}")

print(f"\nTOTAL across segments (some overlap): {total}")
print(f"size bands used: {source.SIZES}")
