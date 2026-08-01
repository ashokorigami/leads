"""App Store triggers - free, global, no auth, and independent of hiring data.

This is what makes markets Apollo cannot see (Latin America, much of Asia)
reachable: job postings there live on local boards Apollo does not index, but
every company's app is in the same store with the same public rating.

Matching matters more than the signal. An app that isn't actually theirs makes
the email wrong in the first sentence, so we verify the seller before believing
anything.
"""
import json, urllib.parse, urllib.request
from datetime import date, datetime
from difflib import SequenceMatcher

STORE = "https://itunes.apple.com/search"

# domain TLD -> App Store country, so we look where the company actually is
TLD_COUNTRY = {"br":"br","mx":"mx","ar":"ar","cl":"cl","co":"co","pe":"pe",
               "in":"in","uk":"gb","de":"de","fr":"fr","es":"es","it":"it",
               "nl":"nl","ch":"ch","se":"se","pl":"pl","au":"au","ca":"ca",
               "jp":"jp","sg":"sg","ae":"ae","za":"za"}


# Apollo country name -> App Store storefront
NAME_COUNTRY = {"switzerland":"ch","brazil":"br","mexico":"mx","chile":"cl",
                "colombia":"co","argentina":"ar","peru":"pe","india":"in",
                "united kingdom":"gb","germany":"de","france":"fr","spain":"es",
                "italy":"it","netherlands":"nl","sweden":"se","poland":"pl",
                "australia":"au","canada":"ca","japan":"jp","singapore":"sg",
                "united arab emirates":"ae","south africa":"za",
                "united states":"us"}


def _country_for(domain: str, country_name: str | None = None) -> str:
    """Company country beats TLD: a Swiss firm on a .com is still Swiss, and
    its apps live in the Swiss storefront."""
    if country_name:
        hit = NAME_COUNTRY.get(country_name.strip().lower())
        if hit:
            return hit
    return TLD_COUNTRY.get(domain.rsplit(".", 1)[-1].lower(), "us")


def _similar(a: str, b: str) -> float:
    clean = lambda s: "".join(c for c in (s or "").lower() if c.isalnum())
    return SequenceMatcher(None, clean(a), clean(b)).ratio()


def _fetch(term: str, country: str, limit: int = 8) -> list[dict]:
    url = f"{STORE}?" + urllib.parse.urlencode(
        {"term": term, "country": country, "entity": "software", "limit": limit})
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r).get("results", [])
    except Exception:
        return []


def find_app(company_name: str, domain: str,
             country_name: str | None = None) -> dict | None:
    """Return the company's own app, or None.

    Match on the SELLER, never the app title. "etrucknow LMV" tells you nothing
    about who owns it; "Kuehne und Nagel (AG & Co.) KG" does. Matching on titles
    produced confident false positives - a competitor's app attributed to the
    prospect, which makes the email wrong in its first sentence.
    """
    country = _country_for(domain, country_name)
    best, best_score = None, 0.0
    for r in _fetch(company_name, country):
        score = max(_similar(company_name, r.get("sellerName")),
                    _similar(company_name, r.get("artistName")))
        if score > best_score:
            best, best_score = r, score
    return best if best_score >= 0.72 else None


def _age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (date.today() - datetime.fromisoformat(
            iso.replace("Z", "+00:00")).date()).days
    except ValueError:
        return None


def triggers_for(company_name: str, domain: str, employees: int | None,
                 country_name: str | None = None) -> list[dict]:
    app = find_app(company_name, domain, country_name)
    out = []

    if not app:
        # Deliberately emit NOTHING here. We cannot prove absence with fuzzy
        # seller matching: Grupo Exito publishes an app with 116,000 ratings
        # under a seller name that does not match "Grupo Exito" closely enough,
        # and telling them they have no app would be wrong in the first
        # sentence. A missed opportunity is cheap; a false claim is not.
        return out

    name  = app.get("trackName")
    rating = app.get("averageUserRating")
    count  = app.get("userRatingCount") or 0
    stale  = _age_days(app.get("currentVersionReleaseDate"))
    url    = app.get("trackViewUrl")

    if rating and count >= 50 and rating < 3.5:
        out.append({"kind": "weak_app", "source": "appstore", "evidence_url": url,
                    "observed_at": None,
                    "detail": f"'{name}' is rated {rating:.1f} from {count:,} ratings "
                              f"on the App Store"})

    if stale and stale > 365:
        out.append({"kind": "weak_app", "source": "appstore", "evidence_url": url,
                    "observed_at": app.get("currentVersionReleaseDate", "")[:10],
                    "detail": f"'{name}' was last updated {stale} days ago "
                              f"(version {app.get('version')})"})

    if employees and employees >= 2000 and count and count < 200:
        out.append({"kind": "weak_app", "source": "appstore", "evidence_url": url,
                    "observed_at": None,
                    "detail": f"'{name}' has only {count} ratings for a company of "
                              f"{employees:,} people"})
    return out
