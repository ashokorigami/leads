import sys, json; sys.path.insert(0, "/opt/origami-outbound/src")
import sender
ids = {c["id"] for c in sender._req("GET", "/campaigns", params={"limit": 100}).get("items", [])
       if c.get("name", "").startswith("origami-")}
found = []
for cid in ids:
    for e in sender._req("GET", "/emails", params={"campaign_id": cid, "limit": 10}).get("items", []):
        found.append(e)
if not found:
    print("NONE"); raise SystemExit
e = found[0]
body = e.get("body") or {}
print("FOUND", len(found), "| from", e.get("from_address_email") or e.get("eaccount"), "| to", e.get("to_address_email_list"),
      "| subject", e.get("subject"), "| ue_type", e.get("ue_type"), "| ts", e.get("timestamp_email") or e.get("timestamp_created"))
print("--- text ---"); print((body.get("text") if isinstance(body, dict) else str(body)) or "(no text part)")
print("--- html ---"); print(((body.get("html") if isinstance(body, dict) else "") or "(no html part)")[:1500])
