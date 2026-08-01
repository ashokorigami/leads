"""Trigger extraction.

A trigger is a SPECIFIC, CHECKABLE FACT about a company that a recipient would
recognise as true. Not "you're growing" - "you've had a Senior iOS Engineer role
open in Austin since 12 May". If we can't name it, it isn't a trigger, and
without a trigger the company is never emailed (enforced by v_sendable).
"""
import re
from datetime import date, datetime

ENG_WORDS = ("software engineer", "software developer", "web developer",
             "application developer", "mobile developer", "mobile engineer",
             "ios", "android",
             "backend", "front end", "frontend", "fullstack", "full stack",
             "platform engineer", "data engineer", "devops", "sre",
             "software architect", "cto", "vp engineering", "web engineer",
             "machine learning", "ml engineer", "ai engineer")

# Engineering roles that are NOT a signal for a software consultancy.
# A hardware or manufacturing hire tells us nothing about their app backlog.
NOT_SOFTWARE = ("mechanical", "electrical", "civil", "industrial", "chemical",
                "manufacturing", "hardware", "biomedical", "aerospace",
                "structural", "process engineer", "field engineer",
                "sales engineer", "solutions engineer", "quality engineer",
                "test engineer", "packaging", "facilities",
                "business develop", "product developer", "cut & sew",
                "foodservice", "brand develop", "market develop")

# Commerce platforms - a store with no app is a concrete mobile pitch
COMMERCE = ("Shopify", "Shopify Plus", "Magento", "WooCommerce", "BigCommerce",
            "Salesforce Commerce Cloud")

def _days_since(s) -> int | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except ValueError:
        return None
    return (date.today() - d).days


def from_jobs(postings: list[dict]) -> list[dict]:
    """Hiring engineers = strongest signal. They need to ship and can't hire fast
    enough. Long-open roles are the strongest variant of it."""
    eng = []
    for j in postings:
        t = (j.get("title") or "").lower()
        if any(b in t for b in NOT_SOFTWARE):
            continue
        # word-boundary match: "cto" must not fire inside "director"
        if not any(re.search(rf"\b{re.escape(w)}\b", t) for w in ENG_WORDS):
            continue
        age = _days_since(j.get("posted_at"))
        if age is None or age > 120:
            continue
        # Zombie-posting guard. Job boards are full of ads that were filled but
        # never taken down. `last_seen_at` is when Apollo last observed the ad
        # LIVE, so require it to be recent - otherwise we would tell someone
        # their role is unfilled when they hired in June, and be wrong in the
        # first sentence to the one reader who knows it.
        seen = _days_since(j.get("last_seen_at"))
        if seen is None or seen > 10:
            continue
        j["_still_listed"] = str(j.get("last_seen_at"))[:10]
        eng.append((j, age))
    if not eng:
        return []
    eng.sort(key=lambda x: -x[1])          # oldest first = most desperate
    job, age = eng[0]
    loc = job.get("city") or job.get("country") or ""
    where = f" in {loc}" if loc else ""
    detail = (f"{len(eng)} engineering role(s) currently listed; longest-running is "
              f"'{job.get('title')}'{where}, posted {str(job.get('posted_at'))[:10]} "
              f"and STILL LISTED as of {job.get('_still_listed')} ({age} days)")
    return [{"kind": "hiring_eng", "detail": detail, "source": "apollo",
             "observed_at": str(job.get("posted_at"))[:10],
             "evidence_url": job.get("url")}]


def from_funding(org: dict) -> list[dict]:
    """Recent round = budget exists and a mandate to ship."""
    age = _days_since(org.get("latest_funding_round_date"))
    if age is None or age > 365:
        return []
    stage = org.get("latest_funding_stage") or "a funding round"
    total = org.get("total_funding_printed")
    extra = f", {total} raised to date" if total else ""
    return [{"kind": "funding", "source": "apollo",
             "detail": f"closed {stage} on "
                       f"{str(org.get('latest_funding_round_date'))[:10]} "
                       f"({age} days ago){extra}",
             "observed_at": str(org.get("latest_funding_round_date"))[:10],
             "evidence_url": None}]


def from_tech(org: dict) -> list[dict]:
    """Commerce platform present = a concrete, checkable starting point."""
    tech = set(org.get("technology_names") or [])
    hits = [t for t in COMMERCE if t in tech]
    if not hits:
        return []
    return [{"kind": "tech_stack", "source": "apollo",
             "detail": f"running {hits[0]} ({len(tech)} technologies detected)",
             "observed_at": None, "evidence_url": None}]


def extract(org: dict, postings: list[dict]) -> list[dict]:
    """All Apollo-derived triggers for one company."""
    return from_jobs(postings) + from_funding(org) + from_tech(org)
