# Origami Outbound

Automated cold-outbound system. Researches companies, writes one specific email
per prospect, routes replies to a rep. Built 2026-07-29/30.

**Host:** `ax41` (5.9.22.220) · `/opt/origami-outbound` · compose project `origami-outbound`
**Database:** Postgres 17 on `127.0.0.1:5434` (5432/5433 belong to Build+ and EDI)
**First real send:** 2026-08-19 (warmup started 2026-07-29, 21 days)

---

## The one rule everything serves

**No nameable buying signal, no email.** A company is only contactable if we can
quote a specific, checkable fact back to the reader — a job ad still listed, a
funding round with a date, an app rated 2.8. If we cannot name it, we do not write.

This is enforced in SQL, not convention. `v_sendable` is the only path to an
email address and it requires a qualifying trigger, a research score >= 70, no
disqualification, a verified address, and no suppression match. Code cannot
bypass it.

---

## Pipeline

```
source.py     Apollo company search   NAICS codes + 21 covered countries
    |
    v         (free) org id kept from search
pipeline.py   PRE-SCREEN: job postings by org id, before paid enrichment
    |         ~60-80% die here at zero credit cost
    v
apollo.py     enrich (1 credit)
    |
    v
triggers.py   hiring / funding / headcount     } nameable facts only
appstore.py   weak app / stale app / adoption  } free, global
    |
    v         no qualifying trigger -> rejected
research.py   Opus 5 scores 0-100, picks the wedge, picks the proof
    |         score < 70 or disqualified -> rejected
    v
prospects.py  find the buyer: seniority search, local title ranking,
    |         reveal only candidates advertising an email,
    |         reject addresses whose domain != the researched company
    v
write.py      Fable 5 writes one email, 70-110 words
    |
    v
emails        approved IS NULL  <-- HUMAN GATE. Nothing sends without TRUE.
    |
    v
sender.py     push to Instantly -> delivery, rotation, warmup pool
    |
    v
replies.py    Opus classifies inbound, routes to the rep with fewest open
```

## Files

| file | does |
|---|---|
| `config.py` | env, DSN, thresholds |
| `llm.py` | model fallback chains |
| `apollo.py` | company search, enrich, job postings |
| `source.py` | volume sourcing by NAICS + geography |
| `triggers.py` | Apollo-derived triggers |
| `appstore.py` | App Store triggers (free, global) |
| `origami_context.py` | capability + proof library, NDA guardrails |
| `research.py` | Opus scoring |
| `prospects.py` | who to email |
| `write.py` | email generation |
| `pipeline.py` | end-to-end orchestration |
| `sender.py` | Instantly push / reply pull |
| `replies.py` | classify + route |
| `review.py` | approval queue + daily digest |

## Running it

```bash
cd /opt/origami-outbound
./.venv/bin/python -c '
import sys; sys.path.insert(0,"src")
import source, pipeline
for seg in ["freight","engineering","construction","manufacturing",
            "insurance","utilities","healthcare","legal","distribution"]:
    source.stage(source.candidates(seg, pages=2))
pipeline.run(source.pending(limit=30))'
```

Review queue / approve / digest:

```python
import review
review.queue()                        # everything awaiting a decision
review.decide([1,2,3], True, "ashok")  # approve
review.digest()                       # the 8am numbers
```

---

## Hard-won gotchas — read before debugging

**Instantly's API blocks some IPs.** Every endpoint returns `403 error code: 1010`
from certain networks, *including with a deliberately invalid key* (a real auth
failure is 401). It works from `ax41`. Do not re-diagnose as a bad key, wrong
scopes, or the wrong plan — all three were wrong guesses. Always call Instantly
from the server.

**Apollo needs two keys.** `APOLLO_API_KEY` for companies/enrich/job-postings,
`APOLLO_MASTER_KEY` for people search. Keys carry per-endpoint scopes; a key with
none selected authenticates fine and 403s on everything.

**`mixed_people/search` is deprecated** -> use `mixed_people/api_search`. It
returns an obfuscated teaser (first name, title, `has_email`); revealing the real
name and address costs a credit via `people/match` with the person `id`.

**Apollo's `person_titles` filter is near-exact and silently returns ZERO.**
Asking for "Chief Information Officer" found nobody at Vitol or Mammoet, both of
which have 50-70 senior people on file. Ask Apollo for seniority only; rank
titles locally.

**Always validate a revealed email's domain against the researched company.**
Apollo returned an `@amentum.com` address on an AECOM search — the person had
changed employer. Emailing her about AECOM's job ad would have been wrong.

**Substring matching on titles is a recurring bug — use `\b` word boundaries.**
It has bitten twice: `"cto"` matched inside `"dire`cto`r"` (Creative Directors
scored as engineering hires) and `"it"` matched inside `"Cred`it` Risk"` (a
credit risk manager scored as an IT buyer). Assume any new keyword list has this
bug until unit-tested against near-misses.

**Never assert what you only inferred.** Four instances so far:
- "no iOS app" when fuzzy matching cannot prove absence (Grupo Exito publishes
  one with 116,000 ratings)
- "unfilled for 74 days" when we only know the ad is *still listed* — plenty of
  ads stay up after a hire. Use `last_seen_at` and say "listed since".
- an app matched by title rather than publisher (an unrelated app attributed to
  Kuehne+Nagel)
- the wrong App Store storefront (a Swiss company searched in the US store)

**A saving you cannot see in the logs probably is not happening.** The
pre-screen was written, deployed, and silently skipped every company for hours
because their rows had no `apollo_org_id`. The tell was the log saying
`no_trigger` where it should have said `no_trigger_prescreen`.

**A provider incident should cost a retry, not a prospect.** Model calls retry
3x; if a whole model family is down the chain falls back to another; a company
that still errors is set back to `sourced` so the next batch retries it.
Previously errored companies were stranded mid-pipeline where nothing looked at
them again.

---

## Measured, not estimated

| | |
|---|---|
| End-to-end survival | ~16-20% of sourced companies produce an email |
| Engineering & construction | **~40%** survival — best segment by far |
| Shipping & maritime | ~8% — Apollo has little hiring data for them |
| Architecture practices | ~0% — they hire architects, not software engineers |
| Pre-screen saving | 11-17 of every 20 companies rejected at zero credit cost |
| Reply classification | 5/5 correct on realistic test replies |

**Volume needed:** ~125 companies sourced per day to sustain 75 emails/day.

## Deliberate constraints

- **Targeting is broad, the message is narrow.** Any industry, any size above
  ~500 — but each company gets ONE specific offer chosen for it. Do not add a
  capability list to an email; it converts a specialist into a generalist.
- **Famous companies score 15-25 points lower.** Ramp and WHOOP get 40 cold
  emails a day; a freight forwarder's IT director gets none. The unglamorous
  middle is the target.
- **Having an in-house team is not a disqualifier.** A software role open 90+
  days means recruiting failed, which is exactly when a vendor gets called.
- **origami.dev never sends cold mail.** Signature and reply-continuation only.
  M365 reputation is tenant-level, and origami.dev shares a tenant with
  eorigami.in and the origamiconsulting domains.
- **No open or click tracking.** Tracking pixels are a spam signal and Apple
  Mail Privacy Protection makes open rates fiction. Reply rate is the only
  metric that correlates with revenue.

## Plan and territory (added 2026-08-01)

The targeting plan is **stored as data, not as a document**, so the pipeline and
the console read the same rows and a plan cannot drift from what actually runs.

| Table | What it holds |
|---|---|
| `regions` | 11 regions, priority-ordered, each tagged `coverage = good \| thin`. The three `thin` regions (LATAM, MEA, rest of Asia) are explicitly on HOLD — a 30-company batch there produced 24 with no trigger, and each miss still burns an enrichment credit. |
| `segments` | 12 segments mapping NAICS + headcount band -> offer (wedge), with the reason written down. |
| `client_proof` | Delivered work the writer may cite, with `nda` and `caution` columns. The NDA row has **no name field at all** — its `label` is already anonymised, so the client name does not exist anywhere the writer can read it. |
| `plan_days` | 31 dated items, weeks 0-4, each with an owner and a target. Tickable from the console. |

Pages: `/plan` (day and week view, countdown to 19 Aug) and `/territory`
(regions, segments, proof library).

**The offer is chosen by size and document load, not by industry.** A
5,000-person insurer and a 5,000-person retailer with 3,000 suppliers both get
Document Intelligence; a 400-person consumer brand gets an app. Below ~1,000
staff, `doc_intelligence` is never offered — pitching a 150,000-document
platform to a company that does not have 150,000 documents reads as a
mass mailing, which is exactly what we are trying not to look like.

### Hosting
Reachable at `outbound.livedemo.co` and (once DNS lands)
`outboundsales.origami.dev` — same app, both behind Caddy basic auth. The
origami.dev block also sets `X-Robots-Tag: noindex` because it sits on the
brand domain.

`eorigami.in` was deliberately NOT used: its root forwards to www.origami.dev
via GoDaddy forwarding IPs, and repointing the A records would have broken that
forward. A subdomain of origami.dev costs one new record and breaks nothing.
Both GoDaddy API tokens returned 401 on 2026-08-01 (from two different hosts,
so expired rather than IP-blocked) — the record has to be added by hand.

## Accounts and login (added 2026-08-01)

Caddy basic_auth is **gone** from both console hosts — it rendered as a browser
popup, which reads as an unfinished tool. The app now authenticates itself.

- `users` — email, name, scrypt password hash, role (`admin` | `rep`), active flag.
- `sessions` — token stored **hashed** (sha256), 30-day expiry. A database dump
  therefore does not hand over live sessions.
- `src/auth.py` — stdlib `hashlib.scrypt`, no new dependency. Cost parameters are
  stored inside the hash string so they can be raised later without invalidating
  anyone's password. `hmac.compare_digest` on verify. A login attempt for an
  unknown address still burns one hash so timing does not reveal whether the
  address exists.
- Enforcement is **one middleware**, not a per-route decorator, so a newly added
  page cannot accidentally ship unprotected. Only `/login` and `/healthz` are open.
- Cookie: `HttpOnly; Secure; SameSite=Lax`.

Pages: `/` is now the dashboard (today's numbers, what needs approving, open
replies, today's plan item). The approval queue moved to `/queue`. `/account`
changes a password.

Create or reset a user:

    cd /opt/origami-outbound
    PYTHONPATH=src .venv/bin/python -c \
      "import auth; auth.create_user('someone@origami.dev','Name','password','admin')"

## Sending domains

`sending_domains` tracks the aging clock — a freshly-registered domain that
starts cold-sending gets filtered, so 30 days of age before warmup is the
cheapest deliverability insurance available. Phase A sends today
(myorigami.co); Phase B is the four origamiconsulting.* (usable ~19 Aug) plus
hireorigami.com, buildwithorigami.com, origamiteams.com and origamibuilds.com
bought 1 Aug (usable ~31 Aug).

## The invented-technology defect (2026-08-01)

Ashok read an approved email and caught it: *"you cannot say inside your own
Azure tenancy — we don't know which server they have."* He was right, and the
emails he had already **approved** were among the wrong ones. Approval is not
verification.

**What shipped:** 12 of 26 emails named a cloud the prospect had never been
observed to use — "sets up in your Azure tenancy" (Boskalis, Van Oord, Clayco,
Ledcor), "your own AWS tenancy" (Kuehne+Nagel, TRC). Four were already approved.

**Where it came from — two places, not one:**
1. `origami_context.py` listed "Azure and AWS" under `# Stack`. That is
   *Origami's* competence; the models read it as a menu to assign to the reader.
2. More seriously, the **scorer** invented it. Opus wrote *"deploys inside
   Boskalis' own Azure tenancy"* into the `angle` field. The writer then
   faithfully carried the instruction into the email. The writer was the
   messenger, not the origin.

**The fix, in three layers:**
- `# Stack` now states explicitly that it is Origami's stack and never an
  assumption about a prospect.
- `research.py` — the `angle` schema forbids naming a cloud/ERP/document system
  that is not in the evidence.
- `write.py` — a **deterministic gate**, `unverified_tech()`. A prompt rule
  drifts back; a regex does not. It rejects the draft and asks for a rewrite,
  up to three corrective passes, then raises rather than shipping.

**The gate's own first version was broken, and the failure is worth
remembering.** It allowed a product name if it appeared in the "evidence", and
evidence was defined as `primary_trigger + angle + wedge + proof_ref`. It caught
every AWS case and **missed every Azure case** — because `angle` is model
output, and the model had written "Azure" there itself. A check that trusts the
thing it is checking is not a check. Evidence is now `primary_trigger` only,
which is built from real Apollo job postings. That single change took the count
from 7 to 12.

Two smaller bugs surfaced in the same audit: joining `research` without
`DISTINCT ON` triple-counted rows (26 emails reported as 48), and because the
bad instruction lived in *stored* data, re-running the writer without scrubbing
the angle would simply have reproduced it.

**Deliberately NOT flagged:** "running inside *their own* cloud tenancy" (that
is our client, and it is true), and "your **AWS** Platform Engineer role" for
Clark Construction — that quotes their real advertised job title, so it is
observed. The gate allows a technology named in the trigger. A gate that
flagged those too would be useless; the unit test asserts both directions.

Re-run the audit any time with:

    cd /opt/origami-outbound && .venv/bin/python tools/rewrite_bad.py        # dry run
    cd /opt/origami-outbound && .venv/bin/python tools/rewrite_bad.py --apply
