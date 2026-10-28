"""People-first sourcing for markets where Apollo's company search is thin.

Apollo's NAICS-based company search misses most of Africa's document-heavy
buyers (banks, telecoms, mining are not in `segments`) and returns
municipalities first. Measured 28 Oct: Instantly SuperSearch holds 234 senior IT
buyers at 1,000+ employee companies in Nigeria, 249 in Egypt, 616 in South
Africa. So this starts from the PERSON:

  1. SuperSearch enrichment (Instantly credits, ~1.5 per lead): senior IT title,
     company HQ in COUNTRY, 1K+ employees, not Government, one lead per
     company. Each lead comes back with a verified work email and its company
     domain.
  2. Each company goes through pipeline.run_one() - Apollo enrich, website
     fetch, Opus research and score - with that person supplied, so no Apollo
     reveal credit is spent on a contact we already hold.
  3. Qualifying companies get a draft in /queue. Nothing sends without approval.

    python3 tools/people_first.py --country Nigeria              # dry run: free count
    python3 tools/people_first.py --country Nigeria --limit 100 --apply

Run it from /opt/origami-outbound, never from /tmp (LESSONS.md sec.8).
"""
import sys
import time

sys.path.insert(0, "/opt/origami-outbound/src")

import pipeline
import sender
from config import db
from prospects import _domain_ok

COUNTRY = sys.argv[sys.argv.index("--country") + 1]
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 100
APPLY = "--apply" in sys.argv
LIST_NAME = f"origami-people-first-{COUNTRY.lower().replace(' ', '-')}"

TITLES = ["Chief Information Officer", "CIO", "Chief Digital Officer", "Chief Technology Officer",
          "IT Director", "Director of Information Technology", "Head of IT",
          "Head of Information Technology", "Head of Digital", "Head of Technology",
          "General Manager, IT", "GM IT", "Head of Digital Transformation"]

FILTERS = {
    "locations": {"include": [{"country": COUNTRY}]},
    "location_mode": "company",
    "title": {"include": TITLES, "includeMode": "CONTAINS"},
    "employeeCount": ["1K - 10K", "10K - 50K", "50K - 100K", "> 100K"],
    "industry": {"exclude": ["Government"]},
    "show_one_lead_per_company": True,
}

n = sender._req("POST", "/supersearch-enrichment/count-leads-from-supersearch",
                json={"search_filters": FILTERS, "show_one_lead_per_company": True}).get("number_of_leads")
print(f"{COUNTRY}: {n} companies with a senior IT buyer in SuperSearch")
if not APPLY:
    print(f"Dry run. --apply enriches up to {LIMIT} (~{LIMIT * 1.5:.0f} Instantly credits).")
    raise SystemExit

prior = [l for l in sender._req("GET", "/lead-lists", params={"limit": 100}).get("items", [])
         if l.get("name") == LIST_NAME]
if prior:
    list_id = prior[0]["id"]
    print(f"reusing list {LIST_NAME} - no new enrichment spent")
else:
    job = sender._req("POST", "/supersearch-enrichment/enrich-leads-from-supersearch", json={
        "search_filters": FILTERS, "limit": LIMIT, "list_name": LIST_NAME,
        "work_email_enrichment": True, "skip_rows_without_email": True})
    list_id = job["resource_id"]
    print(f"enrichment started into {LIST_NAME}")


def all_leads() -> list[dict]:
    out, cur = [], None
    while True:
        body = {"list_id": list_id, "limit": 100}
        if cur:
            body["starting_after"] = cur
        d = sender._req("POST", "/leads/list", json=body)
        out += d.get("items", [])
        cur = d.get("next_starting_after")
        if not cur or not d.get("items"):
            return out


# Asynchronous: wait until the enrichment says it is finished, then read.
deadline = time.time() + 3600
while time.time() < deadline:
    st = sender._req("GET", f"/supersearch-enrichment/{list_id}")
    if not st.get("in_progress"):
        break
    time.sleep(30)
leads = all_leads()
print(f"{len(leads)} leads in list")

by_domain: dict[str, list[dict]] = {}
for l in leads:
    dom = (l.get("company_domain") or "").lower().strip()
    email = (l.get("email") or "").strip().lower()
    if not dom or l.get("verification_status") != 1 or not _domain_ok(email, dom):
        continue
    payload = l.get("payload") or {}
    by_domain.setdefault(dom, []).append({
        "apollo_person_id": None,
        "first_name": l.get("first_name"), "last_name": l.get("last_name"),
        "title": l.get("job_title") or payload.get("jobTitle"),
        "seniority": None, "email": email, "email_status": "verified",
        "linkedin_url": payload.get("linkedIn"),
    })
print(f"{len(by_domain)} companies with a verified, on-domain contact")

tally: dict[str, int] = {}
with db() as conn, conn.cursor() as cur:
    for dom, people in by_domain.items():
        cur.execute("SELECT stage::text FROM companies WHERE domain=%s", (dom,))
        row = cur.fetchone()
        if row and row[0] in ("queued", "qualified", "rejected"):
            outcome = f"skip_already_{row[0]}"      # researched before: no second Opus call
        else:
            cur.execute("""INSERT INTO companies (domain, country, stage, segment)
                           VALUES (%s, %s, 'sourced', 'people_first')
                           ON CONFLICT (domain) DO NOTHING""", (dom, COUNTRY))
            try:
                outcome = pipeline.run_one(cur, dom, preset_people=people[:2])
            except Exception as e:
                cur.execute("UPDATE companies SET stage='sourced', rejected_reason=%s WHERE domain=%s",
                            (f"retry after: {type(e).__name__}", dom))
                outcome = f"error: {type(e).__name__} (requeued)"
        tally[outcome] = tally.get(outcome, 0) + 1
        print(f"  {dom:<30} {outcome}", flush=True)

print("\noutcome tally:")
for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
    print(f"  {v:>4}  {k}")
print("Verify in the database, not from this line.")
