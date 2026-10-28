"""Re-verify every address that is approved-but-unpushed or queued-but-unsent,
and pull the invalid ones before they bounce. 28 Oct: 2 of the first 45 sends
bounced, both from Jul/Aug research.

    python3 tools/reverify.py            # report only
    python3 tools/reverify.py --apply    # unapprove / remove invalid ones

Only 'invalid' is pulled. A catch-all or a verifier that has not answered is
kept: dropping those would drop much of the corporate list for no evidence.
"""
import sys
sys.path.insert(0, "/opt/origami-outbound/src")
import sender
from config import db

APPLY = "--apply" in sys.argv
bad = []
with db() as c, c.cursor() as cur:
    cur.execute("""SELECT e.id, p.email FROM emails e JOIN prospects p ON p.id = e.prospect_id
                    WHERE e.approved AND NOT EXISTS (SELECT 1 FROM sends s WHERE s.email_id = e.id)""")
    reserve = cur.fetchall()

queued = []
for camp in sender._req("GET", "/campaigns", params={"limit": 100})["items"]:
    if not camp["name"].startswith("origami-"):
        continue
    cur_ = None
    while True:
        b = {"campaign": camp["id"], "limit": 100}
        if cur_:
            b["starting_after"] = cur_
        d = sender._req("POST", "/leads/list", json=b)
        queued += [(l["id"], l["email"]) for l in d["items"] if not l.get("timestamp_last_contact")]
        cur_ = d.get("next_starting_after")
        if not cur_ or not d["items"]:
            break

print(f"checking {len(reserve)} approved-unpushed + {len(queued)} queued-unsent", flush=True)
stats = {}
for kind, rows in (("reserve", reserve), ("queued", queued)):
    for key, email in rows:
        st = sender.verify_email(email)
        stats[st] = stats.get(st, 0) + 1
        if st == "invalid":
            bad.append((kind, key, email))
            print(f"  INVALID {kind:8s} {email}", flush=True)
print("results:", stats)

if APPLY and bad:
    with db() as c, c.cursor() as cur:
        for kind, key, email in bad:
            if kind == "reserve":
                cur.execute("""UPDATE emails SET approved = FALSE, approved_by = 'reverify-invalid',
                               approved_at = now() WHERE id = %s""", (key,))
            else:
                # json={}: Instantly 400s an empty body under the client's JSON content-type
                sender._req("DELETE", f"/leads/{key}", json={})
                cur.execute("""UPDATE sends SET status = 'failed', error = 'removed: invalid on re-verify'
                               WHERE provider_msg_id = %s""", (key,))
            cur.execute("""INSERT INTO suppression (kind, value, reason) VALUES ('email', %s, 'reverify-invalid')
                           ON CONFLICT (kind, value) DO NOTHING""", (email.lower(),))
    print(f"pulled {len(bad)}")
