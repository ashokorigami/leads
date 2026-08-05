"""Build the Indian target universe from the NSE listings, not from a hand-typed list.

NSE publishes every listed company (2,389) plus an industry-classified subset.
It does NOT publish websites, and Apollo resolves the names badly - 1 of 8 test
names returned a usable domain, the rest were branch records with no domain at
all. So domains are DERIVED from the name and then VERIFIED by fetching:

  a candidate domain is only accepted if the page we fetch actually mentions
  the company.

Without that check "Supreme Industries Limited" would happily resolve to some
unrelated supreme.com. A domain that cannot be confirmed is left blank rather
than guessed - a wrong domain silently poisons everything downstream.
"""
import csv
import io
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

UA = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
      "Accept-Language": "en-GB,en;q=0.9"}

NSE_FULL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_TOT = "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
NSE_500 = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

# NSE industry -> our segment. Financial Services is deliberately absent except
# where the name says insurance: banks and NBFCs are a different sale.
# Information Technology is excluded outright - they are competitors.
INDUSTRY = {
    "Capital Goods": "manufacturing",
    "Automobile and Auto Components": "manufacturing",
    "Chemicals": "manufacturing",
    "Metals & Mining": "manufacturing",
    "Construction Materials": "manufacturing",
    "Consumer Durables": "manufacturing",
    "Textiles": "manufacturing",
    "Fast Moving Consumer Goods": "manufacturing",
    "Forest Materials": "manufacturing",
    "Healthcare": "pharma",
    "Construction": "engineering",
    "Realty": "engineering",
    "Power": "energy",
    "Oil Gas & Consumable Fuels": "energy",
    "Services": "logistics",
    "Consumer Services": "retail_vendor",
    "Telecommunication": "logistics",
    "Diversified": "manufacturing",
}
EXCLUDE_INDUSTRY = {"Information Technology", "Media Entertainment & Publication"}

STOP = {"limited", "ltd", "ltd.", "the", "and", "of", "co", "company",
        "corporation", "corp", "industries", "india", "indian", "enterprises",
        "group", "holdings", "international", "products", "projects"}

_CLEAN = re.compile(r"[^a-z0-9 ]+")


def tokens(name: str) -> list[str]:
    n = _CLEAN.sub(" ", name.lower())
    return [t for t in n.split() if t and t not in STOP]


def candidates(name: str) -> list[str]:
    t = tokens(name)
    if not t:
        return []
    stems = []
    if len(t) >= 1:
        stems.append(t[0])
    if len(t) >= 2:
        stems.append(t[0] + t[1])
    # keep "india" for names where it is part of the brand (Havells India)
    raw = _CLEAN.sub(" ", name.lower()).split()
    if len(raw) >= 2 and raw[1] == "india":
        stems.append(t[0] + "india")
    out = []
    for s in dict.fromkeys(stems):
        if len(s) < 3:
            continue
        out += [f"{s}.com", f"{s}.co.in", f"{s}.in"]
    return out


def resolves(host: str) -> bool:
    for h in (host, "www." + host):
        try:
            socket.gethostbyname(h)
            return True
        except Exception:
            continue
    return False


def confirm(domain: str, name: str, timeout: float = 10.0) -> tuple[str | None, str]:
    """Return (domain, why) only if the fetched page mentions the company."""
    key = tokens(name)
    if not key:
        return None, "no usable token"
    needle = key[0]
    for host in (domain, "www." + domain):
        try:
            r = httpx.get(f"https://{host}", headers=UA, timeout=timeout,
                          follow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200:
            return None, f"http {r.status_code}"
        body = re.sub(r"<[^>]+>", " ", r.text).lower()
        if needle in body:
            return domain, "confirmed"
        return None, "page does not mention the company"
    return None, "unreachable"


def one(row):
    name, industry, symbol = row["name"], row["industry"], row["symbol"]
    for cand in candidates(name):
        if not resolves(cand):
            continue
        dom, why = confirm(cand, name)
        if dom:
            return {**row, "domain": dom, "status": "confirmed"}
    return {**row, "domain": None, "status": "unresolved"}


def load() -> list[dict]:
    def get(u):
        return httpx.get(u, headers=UA, timeout=40, follow_redirects=True).text

    by_symbol = {}
    for url in (NSE_TOT, NSE_500):
        for r in csv.DictReader(io.StringIO(get(url))):
            sym = (r.get("Symbol") or "").strip()
            ind = (r.get("Industry") or "").strip()
            if not sym or ind in EXCLUDE_INDUSTRY:
                continue
            seg = INDUSTRY.get(ind)
            nm = (r.get("Company Name") or "").strip()
            if not seg:
                # Financial Services only when the name says insurance
                if ind == "Financial Services" and re.search(
                        r"\b(insurance|assurance|life|general)\b", nm, re.I):
                    seg = "insurance"
                else:
                    continue
            by_symbol[sym] = {"symbol": sym, "name": nm,
                              "industry": ind, "segment": seg}
    return list(by_symbol.values())


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    rows = load()
    print(f"NSE classified universe after filtering: {len(rows)} companies")
    if limit:
        rows = rows[:limit]
        print(f"SAMPLE RUN: resolving {len(rows)} to measure the hit rate\n")

    out = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(one, r) for r in rows]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            out.append(r)
            if i % 25 == 0 or limit:
                print(f"  [{i}/{len(rows)}] {r['name'][:34]:36} "
                      f"{r['domain'] or '-'}", flush=True)

    hit = [r for r in out if r["domain"]]
    print(f"\nresolved {len(hit)} of {len(out)}  ({100*len(hit)//max(1,len(out))}%)")
    import json
    json.dump(sorted(out, key=lambda r: r["name"]),
              open("/opt/origami-outbound/nse_universe.json", "w"), indent=2)
