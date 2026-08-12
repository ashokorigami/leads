"""The 08:00 operator digest: compute, log, and email it if a mailer is configured.

review.digest() has existed since the beginning but nothing ever called it on a
schedule and there is no SMTP anywhere in this codebase, so the 8am digest the
plan asks for has never been delivered. This script is what cron runs.

Delivery degrades honestly rather than silently:
  - the digest is ALWAYS written to logs/digest-YYYY-MM-DD.txt
  - it is emailed only if DIGEST_SMTP_HOST / _USER / _PASS / DIGEST_TO are set
  - with no mailer configured it says so on stdout and exits 0, because a cron
    job that fails every morning trains you to ignore cron

The line that matters is stale_warm_replies: an interested reply nobody answered
for four hours. During the ramp that is the number to react to, which is exactly
why this needs to reach a human rather than sit in a table.

    python3 tools/daily_digest.py           # compute, log, send if configured
    python3 tools/daily_digest.py --stdout  # print only, write nothing
"""
import os
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, "/opt/origami-outbound/src")

import review
from config import ENV

ROOT = Path("/opt/origami-outbound")
STDOUT_ONLY = "--stdout" in sys.argv


def setting(key: str, default: str = "") -> str:
    """.env first, environment second. config.py parses .env into a dict and
    never exports it, so os.environ alone would never see these."""
    return ENV.get(key) or os.environ.get(key) or default

d = review.digest()
today = date.today().isoformat()

lines = [f"Origami outbound - digest for {today}", ""]
lines.append(f"  sent yesterday .......... {d['sent_yesterday']}")
lines.append(f"  bounce rate ............. {d['bounce_rate']}%")
lines.append(f"  awaiting your approval .. {d['awaiting_approval']}")
lines.append(f"  companies queued ........ {d['companies_queued']}")
lines.append(f"  replies ................. {d['replies'] or 'none'}")
lines.append(f"  unhandled by rep ........ {d['unhandled_by_rep'] or 'none'}")
lines.append("")
stale = d["stale_warm_replies"]
if stale:
    lines.append(f"  ** {stale} WARM REPLY/REPLIES UNANSWERED FOR 4+ HOURS **")
else:
    lines.append("  no warm reply is sitting unanswered")
lines.append("")
lines.append("  https://outboundsales.origami.dev/queue")
body = "\n".join(lines)

print(body)
if STDOUT_ONLY:
    raise SystemExit

logdir = ROOT / "logs"
logdir.mkdir(exist_ok=True)
(logdir / f"digest-{today}.txt").write_text(body + "\n")

host = setting("DIGEST_SMTP_HOST")
user = setting("DIGEST_SMTP_USER")
pw = setting("DIGEST_SMTP_PASS")
to = setting("DIGEST_TO")
if not all([host, user, pw, to]):
    print("\n[digest] logged only - no mailer configured. To turn on delivery set "
          "DIGEST_SMTP_HOST, DIGEST_SMTP_USER, DIGEST_SMTP_PASS and DIGEST_TO in .env")
    raise SystemExit

msg = EmailMessage()
msg["Subject"] = (f"Outbound digest {today}"
                  + (f" - {stale} WARM REPLY UNANSWERED" if stale else ""))
msg["From"] = user
msg["To"] = to
msg.set_content(body)
try:
    with smtplib.SMTP(host, int(setting("DIGEST_SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)
    print(f"\n[digest] emailed to {to}")
except Exception as ex:
    # Logged already, so a mail outage loses the delivery, never the digest.
    print(f"\n[digest] SEND FAILED ({type(ex).__name__}: {ex}) - digest still written to logs/")
    raise SystemExit(1)
