"""Find a buyer's verified work email through Instantly SuperSearch.

The fallback for qualified companies where Apollo's people data has nobody with
a verified address - measured 28 Oct: 12 of 13 such companies, 8 of them in
South Africa, where SuperSearch holds e.g. 10,398 people at sanlam.co.za.

Cost (Instantly credits, not Apollo): the preview is free; ~1.5 per work email
found and a verification per address kept. find() previews first and spends
nothing when the preview has no one with a buyer title.

Returns the same dict shape as prospects.find(), with apollo_person_id None,
so callers insert both the same way. An address is kept only if the enrichment's own
verification marked it Verified (lead verification_status 1; catch-all is -3
and is refused) and it passes the same company-domain check Apollo addresses
must pass - which matters: on Komatsu, 2 of the 4 addresses SuperSearch found
belonged to people who had since moved to other employers.
"""
import time

import sender
from prospects import TITLES_BY_WEDGE, _domain_ok

EXTRA_TITLES = ["Chief Technology Officer", "Head of IT", "Head of Technology",
                "IT Manager", "Chief Operating Officer"]
WAIT_S = 360


def _variants(domain: str) -> list[str]:
    """Apollo's primary domain is often the .com while staff email from the
    country domain (sanlam.com vs sanlam.co.za); search both."""
    brand = domain.split(".")[0]
    out = [domain]
    for tld in ("co.za", "com.ng", "co.ke", "com.eg", "com.gh", "co.ma", "com"):
        v = f"{brand}.{tld}"
        if v not in out:
            out.append(v)
    return out


def _filters(domain: str, wedge: str | None) -> dict:
    titles = (TITLES_BY_WEDGE.get(wedge or "") or TITLES_BY_WEDGE["doc_intelligence"]) + EXTRA_TITLES
    return {"domains": _variants(domain),
            "title": {"include": titles, "includeMode": "CONTAINS"}}


def preview(domain: str, wedge: str | None = None) -> list[dict]:
    r = sender._req("POST", "/supersearch-enrichment/preview-leads-from-supersearch",
                    json={"search_filters": _filters(domain, wedge)})
    return r.get("leads") or []


def find(domain: str, wedge: str | None = None, want: int = 2) -> list[dict]:
    name = f"origami-contacts-{domain}"
    # A list from an earlier run already holds paid-for addresses; re-read it
    # rather than paying for the same enrichment twice.
    prior = [l for l in sender._req("GET", "/lead-lists", params={"limit": 100}).get("items", [])
             if l.get("name") == name]
    if prior:
        list_id = prior[0]["id"]
    else:
        if not preview(domain, wedge):
            return []
        job = sender._req("POST", "/supersearch-enrichment/enrich-leads-from-supersearch", json={
            "search_filters": _filters(domain, wedge),
            "limit": want * 2,                # some found addresses fail the domain check
            "list_name": name,
            "work_email_enrichment": True,
            "skip_rows_without_email": True,
        })
        list_id = job["resource_id"]

    # Enrichment is asynchronous: leads land in the list as emails are found.
    leads, deadline, last = [], time.time() + WAIT_S, -1
    while time.time() < deadline:
        time.sleep(15)
        items = sender._req("POST", "/leads/list", json={"list_id": list_id, "limit": 50}).get("items", [])
        leads = [l for l in items if l.get("email")]
        pending = [l for l in items if l.get("enrichment_status") not in (None, 1, 2, -1)]
        if len(leads) >= want * 2 or (leads and len(items) == last and not pending):
            break
        last = len(items)

    out = []
    for l in leads:
        if len(out) >= want:
            break
        email = (l["email"] or "").strip().lower()
        if l.get("verification_status") != 1 or not _domain_ok(email, domain):
            continue
        payload = l.get("payload") or {}
        out.append({
            "apollo_person_id": None,
            "first_name": l.get("first_name"),
            "last_name": l.get("last_name"),
            "title": l.get("job_title") or payload.get("jobTitle") or payload.get("title"),
            "seniority": None,
            "email": email,
            "email_status": "verified",
            "linkedin_url": payload.get("linkedIn") or payload.get("linkedin_url"),
        })
    return out
