"""Fetch what a company says about itself, and store it verbatim.

This exists because the hiring-trigger gate was measuring Apollo's job-board
coverage, not fit: 142 of 217 rejections were "no trigger", against 7 for
genuinely poor fit. Whole regions - Latin America, the Gulf, Africa, most of
Asia - were held back purely because Apollo cannot see their job boards.

A company's own site states its plants, fleet, subsidiaries, certifications and
country count. Those are better openers for a document-intelligence pitch than
a job advert, and they exist everywhere in the world.

The text is STORED so the researcher can only quote what was actually fetched.
Model recall is not evidence - that is exactly how "your Azure tenancy" reached
an approved email on 2026-08-01.
"""
import re
import httpx

from config import db

UA = ("Mozilla/5.0 (compatible; OrigamiResearch/1.0; +https://origami.dev) "
      "business-research")

# Pages that describe scale rather than sell. Ordered by how often they carry
# countable facts.
PATHS = ["", "/about", "/about-us", "/company", "/en/about", "/who-we-are",
         "/our-company", "/about/overview", "/en/company", "/corporate"]

_TAG = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.S | re.I)
_ANY = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def _text(html: str) -> str:
    s = _TAG.sub(" ", html)
    s = _ANY.sub(" ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
          .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
    s = _WS.sub(" ", s)
    return _NL.sub("\n\n", s).strip()


def fetch(domain: str, max_pages: int = 3, timeout: float = 12.0) -> list[dict]:
    """Return [{url, text}] for pages we actually retrieved. Never raises."""
    # Two sets, deliberately. Collapsing them meant a page that did NOT
    # redirect matched its own request url and was skipped - vale.com went from
    # 2 pages to 0 and the only reason I noticed was that it had worked before.
    out, asked, got = [], set(), set()
    base = f"https://{domain.strip().lower().removeprefix('www.')}"
    with httpx.Client(follow_redirects=True, timeout=timeout,
                      headers={"User-Agent": UA,
                               # Without this, emirates.com served German and we
                               # would quote German back to an English reader.
                               "Accept-Language": "en-GB,en;q=0.9"}) as c:
        for p in PATHS:
            if len(out) >= max_pages:
                break
            url = base + p
            if url in asked:
                continue
            asked.add(url)
            try:
                r = c.get(url)
            except Exception:
                continue
            if r.status_code != 200 or "html" not in \
                    r.headers.get("content-type", ""):
                continue
            # Dedupe on the RESOLVED url: /about and /about-us both redirected
            # to the same emirates.com page and were stored twice.
            final = str(r.url)
            if final in got:
                continue
            got.add(final)
            t = _text(r.text)
            if len(t) < 400:          # nav-only shell, nothing to quote
                continue
            out.append({"url": final, "text": t[:20000]})
    return out


def store(company_id: int, pages: list[dict]) -> int:
    if not pages:
        return 0
    with db() as c, c.cursor() as cur:
        for p in pages:
            cur.execute(
                """INSERT INTO company_sources (company_id, url, text)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (company_id, url) DO UPDATE
                     SET text = EXCLUDED.text, fetched_at = now()""",
                (company_id, p["url"], p["text"]))
    return len(pages)


def load(company_id: int) -> list[dict]:
    with db() as c, c.cursor() as cur:
        cur.execute("""SELECT url, text FROM company_sources
                       WHERE company_id=%s ORDER BY length(text) DESC""",
                    (company_id,))
        return [{"url": u, "text": t} for u, t in cur.fetchall()]


_NORM = re.compile(r"\s+")


def quote_is_real(quote: str, pages: list[dict]) -> str | None:
    """Return the source URL if `quote` genuinely appears in fetched text.

    Whitespace-insensitive, because the model reflows what it reads. This is
    the deterministic half of the gate: the researcher must QUOTE, and we check
    the quote exists. A fact the model merely remembers cannot pass.
    """
    if not quote or len(quote.strip()) < 12:
        return None
    q = _NORM.sub(" ", quote).strip().lower()
    for p in pages:
        if q in _NORM.sub(" ", p["text"]).strip().lower():
            return p["url"]
    return None
