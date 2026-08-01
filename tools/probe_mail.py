"""Two questions, answered empirically rather than from memory:
   1. Does GoDaddy's public API expose ANY mailbox-creation endpoint?
   2. What does Instantly say about the mailboxes we already connected?
"""
import json
import os
import httpx

GD = next((l.split("=",1)[1].strip() for l in open("/opt/origami-outbound/.env") if l.startswith("GODADDY_PAT=")), "")
GH = {"Authorization": f"Bearer {GD}"}

print("=" * 62)
print("GODADDY — probing for any email / mailbox endpoint")
print("=" * 62)
paths = [
    "/v1/domains/origami.dev",          # control: known-good, proves auth works
    "/v1/email",
    "/v1/emails",
    "/v1/mailboxes",
    "/v1/email/domains/origami.dev",
    "/v1/domains/origami.dev/email",
    "/v1/productivity/email",
    "/v2/customers/me/email",
]
for p in paths:
    try:
        r = httpx.get("https://api.godaddy.com" + p, headers=GH, timeout=20)
        tag = "  <-- CONTROL, must be 200" if p.endswith("origami.dev") else ""
        print(f"  {r.status_code}  {p}{tag}")
    except Exception as e:
        print(f"  ERR {p}: {e}")

print()
print("=" * 62)
print("INSTANTLY — what are the connected mailboxes, and how did they connect?")
print("=" * 62)
key = None
for line in open("/opt/origami-outbound/.env"):
    if line.startswith("INSTANTLY_API_KEY="):
        key = line.split("=", 1)[1].strip()
if not key:
    print("  no key in .env")
    raise SystemExit

IH = {"Authorization": f"Bearer {key}"}
r = httpx.get("https://api.instantly.ai/api/v2/accounts", headers=IH, timeout=30)
print("  GET /api/v2/accounts ->", r.status_code)
if r.status_code == 200:
    items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
    for a in items:
        print("   ", a.get("email"),
              "| provider_code:", a.get("provider_code"),
              "| warmup:", (a.get("warmup_status") if "warmup_status" in a else
                            a.get("warmup", {}).get("status") if isinstance(a.get("warmup"), dict) else "?"),
              "| status:", a.get("status"))
    # provider_code tells us which connection types Instantly actually supports
    print("\n  distinct provider_codes seen:",
          sorted({str(a.get("provider_code")) for a in items}))
else:
    print("   ", r.text[:300])
