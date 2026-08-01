"""Pick WHO to email at a qualified company.

Apollo's model: search returns an obfuscated teaser (first name, title, and a
has_email flag) for free; revealing the real name and address costs a credit.
So: search wide, reveal only candidates that already advertise has_email, and
throw away anything whose revealed address does not belong to the company we
researched - Apollo records go stale and a person who has moved employers would
otherwise receive an email about their OLD job.
"""
import re
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from config import APOLLO_MASTER_KEY

BASE = "https://api.apollo.io/api/v1"
_client = httpx.Client(timeout=45.0, headers={
    "Content-Type": "application/json", "Cache-Control": "no-cache",
    "x-api-key": APOLLO_MASTER_KEY})

# Who we want, in priority order. Broad enough to catch title variants.
TITLES_BY_WEDGE = {
    "doc_intelligence": ["Chief Information Officer", "CIO", "VP Information Technology",
                         "Director of Information Technology", "Head of Digital",
                         "Head of Digital Transformation", "IT Director",
                         "Chief Digital Officer", "Head of Innovation"],
    "dedicated_team":   ["VP Engineering", "Head of Engineering", "CTO",
                         "Director of Engineering", "Chief Technology Officer"],
    "mobile":           ["Head of Product", "VP Product", "CTO", "Head of Mobile",
                         "Head of Digital", "Chief Digital Officer"],
    "commerce":         ["Head of Ecommerce", "VP Ecommerce", "Chief Digital Officer",
                         "Head of Digital", "VP Marketing"],
}
DEFAULT_TITLES = ["CTO", "Chief Information Officer", "VP Engineering",
                  "Head of Digital", "Director of Information Technology"]


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=2, max=20))
def _post(path: str, payload: dict) -> dict:
    r = _client.post(f"{BASE}{path}", json=payload)
    r.raise_for_status()
    return r.json()


# Words that signal the right buyer, weighted. Apollo's person_titles filter is
# near-exact: asking for "Chief Information Officer" returned ZERO at Vitol and
# Mammoet, both of which have 50-70 senior people on file. So we ask Apollo only
# for seniority - which it handles well - and rank titles ourselves.
TITLE_WEIGHTS = {
    "doc_intelligence": {"information technology":10, "cio":10, "information officer":10,
                         "digital":8, "it":8, "technology":7, "data":6,
                         "transformation":6, "innovation":5, "knowledge":5,
                         "information":5, "systems":4},
    "dedicated_team":   {"engineering":10, "cto":10, "technology officer":10,
                         "software":9, "platform":8, "technical":6, "product":5, "data":5},
    "mobile":           {"product":10, "digital":9, "mobile":10, "technology":6,
                         "customer experience":6, "ecommerce":5},
    "commerce":         {"ecommerce":10, "e-commerce":10, "digital":9, "commercial":6,
                         "marketing":5, "customer":5, "revenue":5},
}
NEGATIVE = ("sales", "recruit", "talent", "hr ", "human resources", "procurement",
            "facilities", "health and safety", "hse", "audit", "communications",
            "marketing manager", "account executive")


def _title_score(title: str, wedge: str | None) -> int:
    """Word-boundary matching. Substring matching scored "Credit Risk, Director"
    as an IT buyer because "Credit" contains "it" - the same failure that once
    made "cto" match inside "director"."""
    t = (title or "").lower()
    if any(re.search(rf"\b{re.escape(n)}", t) for n in NEGATIVE):
        return -5
    w = TITLE_WEIGHTS.get(wedge or "", TITLE_WEIGHTS["dedicated_team"])
    return sum(v for k, v in w.items()
               if re.search(rf"\b{re.escape(k)}\b", t))


def search(domain: str, wedge: str | None = None, limit: int = 50) -> list[dict]:
    """Ask Apollo for senior people only, then rank by title relevance here."""
    d = _post("/mixed_people/api_search", {
        "q_organization_domains_list": [domain],
        "person_seniorities": ["c_suite", "vp", "director", "head", "owner"],
        "page": 1, "per_page": limit,
    })
    people = d.get("people") or []
    for p in people:
        p["_score"] = _title_score(p.get("title"), wedge)
    people.sort(key=lambda x: -x["_score"])
    return [p for p in people if p["_score"] >= 6]


def reveal(person_id: str) -> dict | None:
    """Costs a credit. Only call for candidates advertising has_email."""
    return _post("/people/match", {"id": person_id,
                                   "reveal_personal_emails": False}).get("person")


def _domain_ok(email: str, company_domain: str) -> bool:
    """Guard against stale Apollo records: the address must belong to the company
    we actually researched, or the email is about someone's previous job."""
    if not email or "@" not in email:
        return False
    at = email.split("@")[-1].lower()
    cd = company_domain.lower().replace("www.", "")
    root = ".".join(cd.split(".")[-3:]) if cd.count(".") > 1 else cd
    return at == cd or at.endswith("." + cd) or at == root or cd.endswith("." + at)


def find(domain: str, wedge: str | None = None, want: int = 2) -> list[dict]:
    """Search, reveal only promising candidates, keep only verified addresses
    that actually belong to this company."""
    out, spent = [], 0
    for c in search(domain, wedge):
        if len(out) >= want or spent >= 8:      # cap credits per company
            break
        if not c.get("has_email"):
            continue
        spent += 1
        p = reveal(c["id"])
        if not p:
            continue
        email = (p.get("email") or "").strip().lower()
        if p.get("email_status") != "verified":
            continue
        if not _domain_ok(email, domain):
            continue                            # stale record - they moved on
        out.append({
            "apollo_person_id": p.get("id"),
            "first_name": p.get("first_name"),
            "last_name": p.get("last_name"),
            "title": p.get("title"),
            "seniority": p.get("seniority"),
            "email": email,
            "email_status": "verified",
            "linkedin_url": p.get("linkedin_url"),
        })
    return out
