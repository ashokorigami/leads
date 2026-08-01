# Lessons

Every entry here cost real time or shipped a real defect. They are written so
the next person — or the next model — does not pay for them twice.

---

## 1. A check that trusts the thing it checks is not a check

**What happened.** The writer told six companies their platform "sets up in
your Azure tenancy" and two more "your own AWS tenancy". We have no idea what
cloud any of them run. Ashok caught it while reviewing — in emails he had
already **approved**.

**The gate I built to stop it was itself broken.** It allowed a product name if
that name appeared in the *evidence*, and I defined evidence as
`primary_trigger + angle + wedge + proof_ref`. It caught every AWS case and
missed every Azure case.

Why: `angle` is written by the **scoring model**. Opus had itself invented
"deploys inside Boskalis' own Azure tenancy" there. The writer copied the
instruction faithfully; the gate saw "Azure" in its own trusted set and waved it
through. Narrowing evidence to `primary_trigger` alone — the only field built
from real Apollo job data — took the count from 7 to 12 of 26.

**Rule.** When writing a validator, list every field in the trusted set and ask
*who wrote this — a system, or a model?* Model output is the **subject** of
validation, never the **authority** for it.

**How it was found.** Not by the pass count — 7 findings looked like a working
gate. It surfaced only by asking *why did the known-bad Azure cases not appear?*
The control case came from the operator's bug report, not from the gate's own
output.

---

## 2. The gate was measuring the data vendor, not the customer

**What happened.** Every company needed a live job posting to qualify. Ashok
challenged it: *"not every hiring is a requirement… we can create a requirement
as well."*

The rejection table settled it:

| Reason | Count |
|---|---|
| no qualifying trigger | 94 |
| no engineering postings (pre-screen) | 48 |
| sourced by keyword before NAICS filter | 49 |
| no verified contact | 10 |
| **genuinely poor fit or low score** | **~7** |

**142 companies killed for Apollo's blind spots. Seven for being wrong for us.**
Three whole regions — Latin America, the Gulf and Africa, most of Asia — were
marked HOLD, and the stated reason was Apollo's coverage. We had let a data
vendor draw the map of our market.

**Rule.** When a filter rejects overwhelmingly for one reason, check whether
that reason measures the customer or measures your own instrumentation.
Absence of a signal is not evidence of absence of need.

**The fix.** The gate is now *"is there a specific, sourced fact"*, not *"is
there a job advert"*. A company's own website states its plants, fleet,
subsidiaries, certifications and country count — free, global, and true in
markets Apollo cannot see. Proven on Vale (Brazil, zero hiring triggers,
scored 73 on a verified quote from its own supplier page).

---

## 3. Substring matching on titles is a recurring bug — use `\b`

Bit us three times:
- `"cto"` matched inside `"dire`**cto**`r"` → Creative Directors scored as
  engineering hires.
- `"it "` matched inside `"Cred`**it**` Risk, Director"` → a credit risk manager
  scored as an IT buyer.
- bare `"developer"` matched *"Product Developer (Cut & Sew)"* — a garment role.

Assume any new keyword list has this bug until it is tested against the
near-miss cases, not just the hits.

---

## 4. A saving you cannot see in the logs probably is not happening

The free pre-screen was written, deployed, and silently skipped **every**
company, because the rows it depended on had no `apollo_org_id`. Nothing failed.
The only tell was that logs said `no_trigger` where they should have said
`no_trigger_prescreen`.

If an optimisation cannot be observed, instrument it before believing in it.

---

## 5. Every gate needs a control case that must NOT fire

A gate that flags everything is as useless as one that flags nothing, and both
look like success from the count alone.

The unverified-technology test asserts **both** directions:
- must flag: "your Azure tenancy" (invented)
- **must not flag**: "your **AWS** Platform Engineer role" — that quotes
  Clark Construction's real advertised job title, so it is observed
- **must not flag**: "inside *their own* cloud tenancy" — that is our client,
  and it is true

Result: 3 flagged, 3 clean. Had all six flagged, the gate would have been
worthless and the pass count would still have read 6/6.

---

## 6. I broke a working thing while fixing an adjacent one

Fixing duplicate page fetches, I added the resolved URL to the *same* set that
already held the requested URL. Any page that did **not** redirect then matched
itself and was skipped. `vale.com` went from 2 pages to 0.

I only noticed because I had a before-number to compare against. **Re-run what
already worked after every fix** — the regression was in the fix, not the bug.

---

## 7. Verify the API, do not recall it

- **GoDaddy `gd_pat_*` tokens need `Authorization: Bearer`, not `sso-key`.**
  The wrong scheme returns a bare 401 with an empty body — indistinguishable
  from an expired token. I declared two perfectly good tokens dead before
  probing header variants against a known-good control endpoint.
- **GoDaddy's API cannot create mailboxes.** Verified: control call 200, every
  email path 404. It is a registrar API.
- **Apollo's company search returns no location field at all** — no country,
  city, state or address, and `estimated_num_employees` comes back `None`. We
  had been filtering by 21 countries in one call and discarding which matched,
  leaving 612 of 623 companies with no country. Region planning was fiction.
  Sourcing now runs one country at a time and records it.
- **Instantly supports custom IMAP/SMTP**, so Gmail is not required — proven by
  walking its validation errors until it demanded `imap_username`.
- **Instantly's API blocks the dev sandbox IP** (403 code 1010 even with a
  deliberately invalid key — a real auth failure would be 401). Always call it
  from the server.

---

## 8. Never name a module after a stdlib module

`profile.py` shadows Python's stdlib `profile`. Renamed to `company_profile.py`
before it could bite.

This is not hypothetical: a stray `/tmp/inspect.py` on ax41 shadows stdlib
`inspect`, and **any** Python script run from `/tmp` dies with a confusing
`ModuleNotFoundError: No module named 'app'`. It cost a debugging cycle.

---

## 9. Operator approval is not verification

Four of the emails carrying the invented-cloud claim were **already approved**.
The reviewer is reading for tone and plausibility, at speed. They are not a
substitute for a deterministic check, and it is unfair to treat them as one.

Build the check. Let the human catch the class of error, not every instance.

---

## 10. Small operational gotchas

- `psql -c` wraps statements in a single transaction, so a failing `SELECT`
  rolls back the `UPDATE`s before it. Use a file and `-f -`.
- Nested `ssh … "psql -c \"…\""` quoting mangles double quotes into SQL
  identifiers (`column " done=" does not exist`). Write a `.sql` file and pipe it.
- `timeout` is not on macOS by default.
- Caddy will happily accept a site block whose DNS does not resolve yet; it
  retries ACME with exponential backoff and picks the certificate up on its own
  once the record lands.
