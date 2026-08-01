# Architecture

Automated outbound for Origami Consulting LLC. Researches companies, writes one
personalised cold email each, routes replies to a rep. Postgres 17 + FastAPI +
Anthropic + Apollo + Instantly. No build step, no JS framework.

## The flow

```
source ──► enrich ──► signals ──► fetch site ──► research ──► find person
  │           │          │            │             │              │
Apollo     Apollo    job posts    company's      Opus 5        Apollo
NAICS +    (1 credit)  + app       own words     score +       seniority
one                    store       (stored)      quote         search
country                                            │
                                                   ▼
                                              write (Fable 5)
                                                   │
                                          unverified-tech gate
                                                   │
                                            approval queue  ◄── you
                                                   │
                                            Instantly ──► reply ──► classify
                                                                       │
                                                              round-robin to rep
```

## Modules

| File | Does |
|---|---|
| `config.py` | `.env`, DSN, model names, score threshold |
| `llm.py` | Model fallback chains. Research: Opus 5 → 4.8 → Fable. Write: Fable → Opus |
| `apollo.py` | Company search, enrich, job postings, people search |
| `source.py` | NAICS + **one country per call** → staged companies |
| `triggers.py` | Job-posting signals, word-boundary matched, zombie-ad guard |
| `appstore.py` | iTunes lookup. Free, global, no auth. Never claims "no app" |
| `company_profile.py` | Fetches and stores the company's own pages; verifies quotes |
| `origami_context.py` | The capability library and its guardrails |
| `research.py` | Opus 5 scores, picks the wedge, must quote verifiable evidence |
| `prospects.py` | Seniority search + local title ranking |
| `write.py` | Fable 5 writes; deterministic unverified-technology gate |
| `pipeline.py` | Orchestrates the above |
| `sender.py` | Instantly push (must run on the server — it blocks the sandbox IP) |
| `replies.py` | 8-class reply classification, auto-suppression, rep routing |
| `review.py` | Approve / reject / digest |
| `auth.py` | scrypt passwords, hashed session tokens |
| `app.py` | The console |

## The gate

An email may only be sent when **all** of these hold (`v_sendable`):

- the contact's email is `verified`
- research `score >= 70` and no `disqualify_reason`
- at least one trigger exists, of kind `hiring_eng`, `funding`, `exec_hire`,
  `weak_app`, `launch`, `headcount_growth` or **`profile`**
- neither the domain nor the address is suppressed

`profile` is the change made on 2026-08-01: a fact quoted from the company's
own website and **verified to appear in the stored text**. It exists because
requiring a job advert rejected 142 companies for Apollo's blind spots against 7
for genuine poor fit — see `LESSONS.md` §2.

`tech_stack` is deliberately **not** a qualifying kind. "They use Shopify" is
context, not a buying signal.

## Two deterministic gates guard the model

Prompt rules drift back. These do not.

1. **`write.unverified_tech()`** — a technology may be named only if it appears
   in `primary_trigger` (real Apollo job data). Otherwise the draft is rejected
   and rewritten, up to three passes, then it raises rather than shipping.
2. **`company_profile.quote_is_real()`** — the researcher's `evidence_quote`
   must appear, whitespace-insensitively, in text we actually fetched. A
   remembered fact cannot become the opening line.

Both exist because of real defects. Both have unit tests asserting they fire
**and** that they stay silent on the legitimate cases.

## Targeting

Stored as data, not prose, so the plan and the pipeline read the same rows.

| Table | Holds |
|---|---|
| `regions` | 11 regions, priority-ordered, `coverage = good \| research` |
| `segments` | 12 segments: NAICS + headcount band → offer, with the reason |
| `client_proof` | Delivered work the writer may cite, with `nda` and `caution` |
| `plan_days` | Dated plan items with owner and target, tickable in the console |
| `sending_domains` | The 30-day aging clock per domain |

**The offer is chosen by size and document load, not industry.** A 5,000-person
insurer and a 5,000-person retailer with 3,000 suppliers both get Document
Intelligence; a 400-person consumer brand gets an app. Below ~1,000 staff,
`doc_intelligence` is never offered.

## Confidentiality

`client_proof` has an `nda` flag. The NDA row has **no name field at all** — its
`label` is already anonymised, so the client's name does not exist anywhere the
writer can read it. That is deliberate: a flag can be ignored by a model, an
absent field cannot be read.

The FanRush row carries an attribution warning: the brands FanRush lists are
*its* clients, not Origami's, and must never be implied otherwise.

## Deliverability

- Cold mail never goes from `origami.dev`. It carries the signature and
  reply-continuation only.
- Microsoft 365 reputation is **tenant-level**, and origami.dev shares its
  tenant with eorigami.in. Cold-send complaints there could throttle real client
  mail. Hence Google Workspace (`myorigami.co`) carries the volume.
- Plain-text signature, real postal address (CAN-SPAM), one-click opt-out.
  Never an image signature.
- A rep replies from the **same** address the cold mail left from; switching
  mid-thread breaks threading and reads as phishing.

## Console

`https://outboundsales.origami.dev` and `https://outbound.livedemo.co`.
Login is enforced in **one middleware**, not per route, so a new page cannot
ship unprotected. Only `/login` and `/healthz` are open.

| Page | Shows |
|---|---|
| `/` | Today: what needs approving, open replies, today's plan item |
| `/queue` | The approval queue, full text of every email |
| `/targets` | Every company by name — country, size, segment, offer, score |
| `/contacted` | Everyone mailed or queued, with CSV export, so nobody double-mails |
| `/plan` | Day and week view, countdown to launch |
| `/territory` | Regions, segments, the proof library |
| `/health` | Mailboxes, pipeline stages, today's digest |

## Deployment

`ax41` (5.9.22.220), `/opt/origami-outbound`, compose project
`origami-outbound`, Postgres on `127.0.0.1:5434`. Web via systemd
`origami-outbound-web` on `127.0.0.1:8120`, fronted by Caddy.

Secrets live in `.env` (chmod 600, git-ignored) and nowhere else.
