"""What location fields does Apollo's org SEARCH actually return?
We filter by country, so the answer decides whether we can record it for free."""
import sys, json
sys.path.insert(0, "/opt/origami-outbound/src")
import apollo

d = apollo.search_companies(
    page=1, per_page=3,
    organization_num_employees_ranges=["1001,5000"],
    organization_naics_codes=["541330"],           # engineering services
    organization_locations=["Germany"])

orgs = d.get("organizations") or d.get("accounts") or []
print("orgs returned:", len(orgs))
if orgs:
    o = orgs[0]
    print("\nall keys:", sorted(o.keys()))
    print("\nanything location-ish:")
    for k in sorted(o):
        if any(t in k.lower() for t in
               ("countr", "city", "state", "location", "address", "hq", "raw")):
            print(f"  {k} = {o[k]!r}")
    print("\nfirst org summary:")
    for k in ("name", "primary_domain", "estimated_num_employees"):
        print(f"  {k} = {o.get(k)!r}")
