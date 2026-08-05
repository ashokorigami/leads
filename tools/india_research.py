"""Research Indian companies for the Document Intelligence offer.

Candidates come from general knowledge, which is fine - a candidate is a
hypothesis. The SCORE and the OPENING FACT come only from text fetched from the
company's own website and verified to contain the quote. Nothing here is
written from recall.

Vedanta and Sterlite are deliberately absent: they are the NDA client.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/opt/origami-outbound/src")
import company_profile
import research

# (domain, name, segment) - document-heavy, regulated, or vendor-heavy at scale.
CANDIDATES = [
    # Electrical & industrial manufacturing - the Havells shape
    ("havells.com", "Havells India", "manufacturing"),
    ("polycab.com", "Polycab India", "manufacturing"),
    ("finolexcables.com", "Finolex Cables", "manufacturing"),
    ("crompton.co.in", "Crompton Greaves Consumer Electricals", "manufacturing"),
    ("kei-ind.com", "KEI Industries", "manufacturing"),
    ("vguard.in", "V-Guard Industries", "manufacturing"),
    ("bajajelectricals.com", "Bajaj Electricals", "manufacturing"),
    ("aparindustries.com", "Apar Industries", "manufacturing"),

    # Automotive & heavy engineering
    ("tatamotors.com", "Tata Motors", "manufacturing"),
    ("mahindra.com", "Mahindra & Mahindra", "manufacturing"),
    ("ashokleyland.com", "Ashok Leyland", "manufacturing"),
    ("bharatforge.com", "Bharat Forge", "manufacturing"),
    ("tvsmotor.com", "TVS Motor", "manufacturing"),
    ("motherson.com", "Samvardhana Motherson", "manufacturing"),
    ("sundram.com", "Sundram Fasteners", "manufacturing"),

    # Pharmaceuticals - heavily audited, submission-driven
    ("sunpharma.com", "Sun Pharmaceutical", "pharma"),
    ("cipla.com", "Cipla", "pharma"),
    ("drreddys.com", "Dr. Reddy's Laboratories", "pharma"),
    ("lupin.com", "Lupin", "pharma"),
    ("torrentpharma.com", "Torrent Pharmaceuticals", "pharma"),
    ("zyduslife.com", "Zydus Lifesciences", "pharma"),
    ("aurobindo.com", "Aurobindo Pharma", "pharma"),
    ("divislabs.com", "Divi's Laboratories", "pharma"),
    ("glenmarkpharma.com", "Glenmark Pharmaceuticals", "pharma"),
    ("alkemlabs.com", "Alkem Laboratories", "pharma"),

    # Energy & utilities - permits, inspections, decades of asset records
    ("ntpc.co.in", "NTPC", "energy"),
    ("powergrid.in", "Power Grid Corporation of India", "energy"),
    ("tatapower.com", "Tata Power", "energy"),
    ("torrentpower.com", "Torrent Power", "energy"),
    ("adanipower.com", "Adani Power", "energy"),

    # Metals & mining
    ("tatasteel.com", "Tata Steel", "manufacturing"),
    ("jsw.in", "JSW Group", "manufacturing"),
    ("hindalco.com", "Hindalco Industries", "manufacturing"),
    ("jindalsteelpower.com", "Jindal Steel & Power", "manufacturing"),
    ("sail.co.in", "Steel Authority of India", "manufacturing"),
    ("nmdc.co.in", "NMDC", "manufacturing"),

    # Cement - multi-plant, permit and compliance heavy
    ("ultratechcement.com", "UltraTech Cement", "manufacturing"),
    ("ambujacement.com", "Ambuja Cements", "manufacturing"),
    ("shreecement.com", "Shree Cement", "manufacturing"),
    ("dalmiabharat.com", "Dalmia Bharat", "manufacturing"),
    ("jkcement.com", "JK Cement", "manufacturing"),

    # Chemicals
    ("srf.com", "SRF Limited", "manufacturing"),
    ("aartiindustries.com", "Aarti Industries", "manufacturing"),
    ("deepaknitrite.com", "Deepak Nitrite", "manufacturing"),
    ("piindustries.com", "PI Industries", "manufacturing"),
    ("upl-ltd.com", "UPL", "manufacturing"),

    # Insurance - claims files and policy documents; the strongest fit of all
    ("hdfclife.com", "HDFC Life Insurance", "insurance"),
    ("icicilombard.com", "ICICI Lombard", "insurance"),
    ("sbilife.co.in", "SBI Life Insurance", "insurance"),
    ("bajajallianz.com", "Bajaj Allianz", "insurance"),
    ("maxlifeinsurance.com", "Max Life Insurance", "insurance"),
    ("starhealth.in", "Star Health Insurance", "insurance"),

    # Infrastructure & EPC - drawings, submittals, RFIs, closeout
    ("larsentoubro.com", "Larsen & Toubro", "engineering"),
    ("kecrpg.com", "KEC International", "engineering"),
    ("kalpataruprojects.com", "Kalpataru Projects International", "engineering"),
    ("ncclimited.com", "NCC Limited", "engineering"),
    ("afcons.com", "Afcons Infrastructure", "engineering"),

    # Large retail - the vendor angle
    ("relianceretail.com", "Reliance Retail", "retail_vendor"),
    ("dmartindia.com", "Avenue Supermarts (DMart)", "retail_vendor"),
    ("trentlimited.com", "Trent Limited", "retail_vendor"),

    # Logistics - bills of lading, customs, certificates of origin
    ("delhivery.com", "Delhivery", "logistics"),
    ("bluedart.com", "Blue Dart Express", "logistics"),
    ("allcargologistics.com", "Allcargo Logistics", "logistics"),
    ("mahindralogistics.com", "Mahindra Logistics", "logistics"),
    ("concorindia.co.in", "Container Corporation of India", "logistics"),

    # Textiles - export documentation, compliance certificates
    ("arvind.com", "Arvind Limited", "manufacturing"),
    ("welspunliving.com", "Welspun Living", "manufacturing"),
    ("tridentindia.com", "Trident Group", "manufacturing"),
    ("vardhman.com", "Vardhman Textiles", "manufacturing"),
]


def one(item):
    domain, name, segment = item
    rec = {"domain": domain, "name": name, "segment": segment,
           "pages": 0, "score": None, "wedge": None, "trigger": None,
           "quote": None, "url": None, "error": None, "unverified": None}
    try:
        pages = company_profile.fetch(domain, max_pages=3)
        rec["pages"] = len(pages)
        if not pages:
            rec["error"] = "site unreachable or blocked"
            return rec
        org = {"name": name, "primary_domain": domain, "country": "India",
               "industry": segment}
        r = research.research(org, [], pages)
        rec.update(
            score=r.get("score"),
            wedge=r.get("wedge"),
            trigger=(r.get("primary_trigger") or "")[:400],
            angle=(r.get("angle") or "")[:400],
            quote=r.get("evidence_quote") or None,
            url=r.get("evidence_url"),
            unverified=r.get("quote_unverified"),
            reasoning=(r.get("reasoning") or "")[:300],
            disqualify=r.get("disqualify_reason"),
        )
    except Exception as ex:
        rec["error"] = f"{type(ex).__name__}: {ex}"[:200]
    return rec


if __name__ == "__main__":
    out = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(one, c): c for c in CANDIDATES}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            out.append(r)
            flag = (r["error"] or
                    (f"score {r['score']}" + ("" if r["url"] else "  [QUOTE UNVERIFIED]")))
            print(f"[{i}/{len(CANDIDATES)}] {r['name'][:38]:40} {flag}", flush=True)
    out.sort(key=lambda r: -(r["score"] or 0))
    with open("/opt/origami-outbound/india_targets.json", "w") as fh:
        json.dump(out, fh, indent=2)
    ok = [r for r in out if r["score"]]
    print(f"\nresearched {len(ok)} of {len(CANDIDATES)}; "
          f"{sum(1 for r in ok if (r['score'] or 0) >= 70)} score 70+; "
          f"{sum(1 for r in ok if r['url'])} with a VERIFIED quote")
