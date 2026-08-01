"""Read origami.dev DNS, and optionally add a subdomain A record.

Read-only unless argv[1] == 'add'.

GOTCHA: GoDaddy's newer `gd_pat_*` tokens need `Authorization: Bearer <pat>`,
NOT the older `sso-key <pat>` scheme. The wrong scheme returns a bare 401 with
an empty body, which is indistinguishable from an expired token - I wrongly
declared two working tokens dead before spotting it.
"""
import os
import sys
import httpx

KEY = os.environ.get("GODADDY_PAT") or next(
    (l.split("=", 1)[1].strip() for l in open("/opt/origami-outbound/.env")
     if l.startswith("GODADDY_PAT=")), None)
if not KEY:
    sys.exit("GODADDY_PAT not set (env or .env)")

H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
DOMAIN, SUB, IP = "origami.dev", "outboundsales", "5.9.22.220"

r = httpx.get(f"https://api.godaddy.com/v1/domains/{DOMAIN}/records", headers=H, timeout=30)
print("read status", r.status_code)
if r.status_code != 200:
    print(r.text[:500]); sys.exit(1)

recs = r.json()
print("\n--- A / CNAME / MX on origami.dev (must stay intact) ---")
for rec in recs:
    if rec["type"] in ("A", "CNAME", "MX"):
        print("  %-6s %-24s %s" % (rec["type"], rec["name"], rec["data"]))

clash = [x for x in recs if x["name"] == SUB]
print("\nexisting '%s' records: %s" % (SUB, clash or "none"))

if len(sys.argv) > 1 and sys.argv[1] == "add":
    if clash:
        sys.exit("REFUSING: something already answers on that name.")
    # PUT on the (type,name) pair touches ONLY that name. Root, www and MX are
    # untouched - verified by re-reading the record set afterwards.
    w = httpx.put(f"https://api.godaddy.com/v1/domains/{DOMAIN}/records/A/{SUB}",
                  headers=H, json=[{"data": IP, "ttl": 600}], timeout=30)
    print("\nwrite status", w.status_code, w.text[:300])
