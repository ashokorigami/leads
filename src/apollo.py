"""Apollo client. Three stages, cheapest first:
   search()       - wide, thin records, no credit cost
   enrich()       - full firmographics + technographics, costs a credit
   job_postings() - the strongest buying signal
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from config import APOLLO_KEY

BASE = "https://api.apollo.io/api/v1"
_H = {"Content-Type": "application/json", "Cache-Control": "no-cache",
      "x-api-key": APOLLO_KEY}
_client = httpx.Client(timeout=45.0, headers=_H)


@retry(stop=stop_after_attempt(4),
       wait=wait_exponential_jitter(initial=2, max=30))
def _post(path: str, payload: dict) -> dict:
    r = _client.post(f"{BASE}{path}", json=payload)
    if r.status_code == 429:
        raise RuntimeError("apollo rate limited")
    r.raise_for_status()
    return r.json()


@retry(stop=stop_after_attempt(4),
       wait=wait_exponential_jitter(initial=2, max=30))
def _get(path: str) -> dict:
    r = _client.get(f"{BASE}{path}")
    if r.status_code == 429:
        raise RuntimeError("apollo rate limited")
    r.raise_for_status()
    return r.json()


def search_companies(page: int = 1, per_page: int = 25, **filters) -> dict:
    """Wide + thin. Returns {'organizations': [...], 'pagination': {...}}.
    Deliberately NOT filtered by industry - we target on buying signal."""
    return _post("/mixed_companies/search",
                 {"page": page, "per_page": per_page, **filters})


def enrich(domain: str) -> dict | None:
    """Full org record: funding dates, technologies, headcount by dept."""
    return _post("/organizations/enrich", {"domain": domain}).get("organization")


def job_postings(org_id: str) -> list[dict]:
    d = _get(f"/organizations/{org_id}/job_postings")
    return d.get("organization_job_postings") or d.get("job_postings") or []


def search_people(org_id: str, titles: list[str], per_page: int = 10) -> list[dict]:
    d = _post("/mixed_people/search", {
        "organization_ids": [org_id],
        "person_titles": titles,
        "page": 1, "per_page": per_page,
    })
    return d.get("people") or d.get("contacts") or []
