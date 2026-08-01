"""Find candidate companies at volume.

Targets the unglamorous middle deliberately: large, old, document-heavy firms
in industries nobody else is cold-emailing. Famous tech companies are excluded
at the scoring stage, so there is no point spending search quota on them here.
"""
import apollo
from config import db

# NAICS beats keyword tags. Keyword search matched "Civil Engineering
# Discoveries" (a content site) and "Business Insurance" (a trade magazine)
# because their keywords mention the industry. NAICS is what a company IS.
SEGMENTS = {
    "freight":       ["488510", "484121", "483111", "488320"],   # forwarding, trucking, sea, courier
    "warehousing":   ["493110", "493120", "488210", "488310"],
    "engineering":   ["541330", "541310", "541320", "541350"],   # engineering, architecture, survey
    "construction":  ["236220", "237310", "237990", "238210"],
    "manufacturing": ["333120", "325180", "332710", "336390", "327320"],
    "insurance":     ["524126", "524210", "524292", "524130"],
    "utilities":     ["221112", "221310", "221122", "486210"],
    "healthcare":    ["622110", "621999", "541714", "325412"],
    "legal":         ["541110", "541199"],
    "distribution":  ["423830", "424690", "423610", "424410"],
    # Large buyers with thousands of suppliers. Not "document-heavy" by
    # reputation, but drowning in vendor contracts, onboarding packets,
    # compliance and insurance certificates, POs and invoices.
    "retail":        ["452210", "455110", "444110", "445110", "448140", "441110"],
    "wholesale":     ["424410", "423450", "424310", "423120"],
    "food_mfg":      ["311612", "311421", "311511", "312111"],
    "pharma_med":    ["325412", "339112", "424210"],
}

# Big enough for budget, not so big they have an army of in-house engineers.
SIZES = ["501,1000", "1001,5000", "5001,10000"]

# Apollo's job-posting coverage is US / Western-Europe heavy. Batch 2 sourced 30
# companies across Turkey, India, Saudi, South Africa, NZ, Malaysia and Egypt:
# 24 of 30 produced NO trigger at all, because Apollo simply has no hiring data
# there. Every one still cost an enrichment credit. So restrict sourcing to
# markets where a trigger can actually be found, and reach the rest through
# app-store signals or a different data source rather than paying to guess.
COVERED = ["United States", "United Kingdom", "Canada", "Australia", "Ireland",
           "Germany", "France", "Netherlands", "Spain", "Italy", "Sweden",
           "Belgium", "Switzerland", "Denmark", "Norway", "Finland", "Austria",
           "Poland", "Portugal", "New Zealand", "Singapore"]


def candidates(segment: str, country: str | None = None,
               pages: int = 3, per_page: int = 25) -> list[dict]:
    """Return {domain, name, employees, country, growth} for one segment.

    Pass ONE country. Apollo's org search returns no location field whatsoever
    (verified 2026-08-01: the payload has no country, city, state or address
    key, and estimated_num_employees comes back None), so the only way to know
    where a sourced company is, is to ask one country at a time and record what
    we asked for. Searching all 21 covered countries in a single call is
    cheaper and is what we used to do - it left 612 of 621 companies with no
    country at all, which made region planning impossible.
    """
    seen, out = set(), []
    for page in range(1, pages + 1):
        try:
            d = apollo.search_companies(
                page=page, per_page=per_page,
                organization_num_employees_ranges=SIZES,
                organization_naics_codes=SEGMENTS[segment],
                organization_locations=[country] if country else COVERED)
        except Exception:
            break
        orgs = d.get("organizations") or d.get("accounts") or []
        if not orgs:
            break
        for o in orgs:
            dom = (o.get("primary_domain") or "").lower().strip()
            if not dom or dom in seen:
                continue
            seen.add(dom)
            out.append({
                "domain": dom,
                "apollo_org_id": o.get("id"),
                "name": o.get("name"),
                "employees": o.get("estimated_num_employees"),
                # Apollo does not return it; the country we FILTERED on is the
                # only truthful source. None when sourcing the whole covered list.
                "country": o.get("country") or country,
                "growth_12m": o.get("organization_headcount_twelve_month_growth"),
                "segment": segment,
            })
    return out


def stage(rows: list[dict]) -> int:
    """Park candidates in `companies` as 'sourced'. The pipeline picks them up
    from there, so sourcing and enrichment can run at different rates."""
    n = 0
    with db() as conn, conn.cursor() as cur:
        for r in rows:
            cur.execute("SELECT 1 FROM suppression WHERE kind='domain' AND value=%s",
                        (r["domain"],))
            if cur.fetchone():
                continue
            cur.execute("""INSERT INTO companies (domain, apollo_org_id, name,
                           employees, country, segment, stage)
                           VALUES (%s,%s,%s,%s,%s,%s,'sourced')
                           ON CONFLICT (domain) DO UPDATE SET
                             apollo_org_id = COALESCE(companies.apollo_org_id,
                                                      EXCLUDED.apollo_org_id),
                             country = COALESCE(companies.country,
                                                EXCLUDED.country),
                             segment = COALESCE(companies.segment,
                                                EXCLUDED.segment)""",
                        (r["domain"], r.get("apollo_org_id"), r["name"],
                         r["employees"], r["country"], r.get("segment")))
            n += cur.rowcount
    return n


def pending(limit: int = 50) -> list[str]:
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT domain FROM companies WHERE stage='sourced'
                       ORDER BY employees DESC NULLS LAST LIMIT %s""", (limit,))
        return [r[0] for r in cur.fetchall()]
