"""Poll Instantly for inbound replies and route them. What cron runs.

sender.pull_replies() has existed since the beginning and was never called by
anything - no cron, no route in app.py. A prospect who replied would sit in
Instantly's Unibox: never classified, never routed to a rep, never counted in
the digest's stale_warm_replies. An unworked positive reply is worse than one
never generated, so this is the piece that has to run unattended.

Polling rather than a webhook is deliberate: a webhook would mean a public,
session-exempt route on a console where auth is otherwise enforced in one
middleware, plus a shared secret to manage. The digest's SLA on a warm reply is
four hours; a ten-minute poll is well inside it and adds no attack surface.

A lookback window wider than the poll interval is intentional - pull_replies()
dedupes on (from_email, subject), so overlapping windows cost nothing and a
missed run does not drop a reply.

    python3 tools/pull_replies.py            # last 2 hours
    python3 tools/pull_replies.py --hours 24
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/origami-outbound/src")

import sender

HOURS = 2
if "--hours" in sys.argv:
    HOURS = int(sys.argv[sys.argv.index("--hours") + 1])

since = (datetime.now(timezone.utc) - timedelta(hours=HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

try:
    n = sender.pull_replies(since_iso=since)
except Exception as ex:
    # Loud on stderr so the cron log carries it; a poller that swallows its own
    # failure is indistinguishable from a quiet inbox.
    print(f"{stamp}  pull_replies FAILED: {type(ex).__name__}: {ex}", file=sys.stderr)
    raise SystemExit(1)

print(f"{stamp}  ingested {n} new repl{'y' if n == 1 else 'ies'} (since {since})")
