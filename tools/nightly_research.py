"""Nightly research: keep /queue stocked for 75 sends a weekday.

Research only ever ran by hand, so after the 28 Oct runs nothing new reached
/queue and the 29 Oct push left the approved reserve at zero. This runs the
EXPENSIVE half (pipeline.run_one: Apollo enrich, Opus research, Apollo reveal,
Fable write) every weeknight until enough NEW companies have a draft, or a
company cap is hit - whichever comes first. The cap is the spend ceiling.

Yield measured 28 Oct: US 4 queued of 15 (27%), South Africa 1 of 15 twice.
One email per company sends, and review drops some, so the target is companies
queued, not emails written.

Guards, because this runs unattended and every company costs credits:
  - a preflight Opus call before any Apollo credit is spent (28 Oct: a dead
    Anthropic key burned Apollo credits on 19 companies before anyone noticed)
  - stops after 3 consecutive errors
  - never researches a company we have already emailed
  - stages more US companies (free search, no credit) when the pool runs low

    python3 tools/nightly_research.py                  # dry run: pool and plan only
    python3 tools/nightly_research.py --apply
    python3 tools/nightly_research.py --apply --target 90 --max-companies 350

Run it from /opt/origami-outbound, never from /tmp (LESSONS.md sec.8).
"""
import re
import subprocess
import sys
import time

sys.path.insert(0, "/opt/origami-outbound/src")

import pipeline
from config import db, MODEL_RESEARCH

APPLY = "--apply" in sys.argv
TARGET = 90            # new companies with a draft; 75 sends + ~20% lost in review
MAX_COMPANIES = 350    # spend ceiling per night
COUNTRY = "United States"
MAX_CONSECUTIVE_ERRORS = 3
if "--target" in sys.argv:
    TARGET = int(sys.argv[sys.argv.index("--target") + 1])
if "--max-companies" in sys.argv:
    MAX_COMPANIES = int(sys.argv[sys.argv.index("--max-companies") + 1])
if "--country" in sys.argv:
    COUNTRY = sys.argv[sys.argv.index("--country") + 1]

POOL_SQL = """
    SELECT c.domain FROM companies c
     WHERE c.stage::text = 'sourced' AND c.country = %s
       AND NOT EXISTS (SELECT 1 FROM suppression s
                        WHERE s.kind='domain' AND s.value = c.domain)
       AND NOT EXISTS (SELECT 1 FROM sends sn
                         JOIN emails e ON e.id = sn.email_id
                         JOIN prospects p ON p.id = e.prospect_id
                        WHERE p.company_id = c.id)
     ORDER BY c.employees DESC NULLS LAST
     LIMIT %s"""


def stamp(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())}  {msg}", flush=True)


def pool(limit: int) -> list[str]:
    with db() as c, c.cursor() as cur:
        cur.execute(POOL_SQL, (COUNTRY, limit))
        return [r[0] for r in cur.fetchall()]


def preflight() -> None:
    """One tiny Opus call. If the key or billing is dead, stop BEFORE Apollo spends."""
    from research import _client
    _client.messages.create(model=MODEL_RESEARCH, max_tokens=5,
                            messages=[{"role": "user", "content": "ok"}])


domains = pool(MAX_COMPANIES)
stamp(f"{COUNTRY}: {len(domains)} sourced companies in the pool "
      f"(target {TARGET} queued, cap {MAX_COMPANIES} companies)")

if len(domains) < MAX_COMPANIES:
    # Sourcing is search + INSERT only - no enrichment credit, no LLM call.
    for pri in (1, 2, 3):
        if len(domains) >= MAX_COMPANIES:
            break
        cmd = [sys.executable, "tools/source_us.py", "--country", COUNTRY,
               "--priority", str(pri), "--pages", "10"] + (["--apply"] if APPLY else [])
        stamp(f"pool low - staging: {' '.join(cmd[1:])}")
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        print(out.stdout[-1500:] + out.stderr[-1500:], flush=True)
        domains = pool(MAX_COMPANIES)
        stamp(f"pool now {len(domains)}")

if not APPLY:
    stamp("dry run - nothing researched. Re-run with --apply.")
    raise SystemExit

try:
    preflight()
except Exception as e:
    stamp(f"ABORT: preflight Opus call failed ({type(e).__name__}: {e}) - no credits spent")
    raise SystemExit(2)

tally: dict[str, int] = {}
queued = errors_in_row = tried = 0
with db() as conn, conn.cursor() as cur:
    for d in domains:
        if queued >= TARGET:
            break
        tried += 1
        try:
            outcome = pipeline.run_one(cur, d, verbose=False)
            errors_in_row = 0
        except Exception as e:
            cur.execute("""UPDATE companies SET stage='sourced', rejected_reason=%s
                            WHERE domain=%s""", (f"retry after: {type(e).__name__}", d))
            outcome = f"error: {type(e).__name__}"
            errors_in_row += 1
        if outcome.startswith("queued_"):
            queued += 1
        key = re.sub(r"_\d.*", "", outcome)     # queued_83_1emails -> queued
        tally[key] = tally.get(key, 0) + 1
        stamp(f"{tried:>4} {d:<32} {outcome}   [queued {queued}/{TARGET}]")
        if errors_in_row >= MAX_CONSECUTIVE_ERRORS:
            stamp(f"ABORT: {errors_in_row} errors in a row - stopping to protect credits")
            break

stamp(f"done: {tried} companies tried, {queued} newly queued (target {TARGET})")
for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
    print(f"  {v:>4}  {k}")
if queued < TARGET:
    stamp(f"WARNING: short by {TARGET - queued} - tomorrow's /queue will not cover 75 sends")
print("Verify in the database, not from this line.")
sys.exit(0 if queued >= TARGET else 1)
