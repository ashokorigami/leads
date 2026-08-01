"""Approval gate + daily digest.

Approval is deliberately a separate, explicit step. Nothing in the send path
can pick up an email that a human has not marked approved=TRUE.
"""
from datetime import date, timedelta
from config import db


def queue() -> list[dict]:
    """Everything awaiting a decision, newest research only."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (p.id)
                   e.id, c.name, p.first_name, p.last_name, p.title, p.email,
                   r.score, r.wedge, e.subject, e.body
            FROM emails e
            JOIN prospects p ON p.id = e.prospect_id
            JOIN companies c ON c.id = p.company_id
            JOIN research  r ON r.company_id = c.id
            WHERE e.approved IS NULL
            ORDER BY p.id, r.created_at DESC""")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def decide(email_ids: list[int], approved: bool, by: str = "ashok") -> int:
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE emails SET approved=%s, approved_by=%s, approved_at=now()
                       WHERE id = ANY(%s) AND approved IS NULL""",
                    (approved, by, email_ids))
        return cur.rowcount


def digest(day: date | None = None) -> dict:
    """The 8am email. Deliberately short - a digest nobody reads is worthless."""
    day = day or date.today()
    y = day - timedelta(days=1)
    with db() as conn, conn.cursor() as cur:
        out = {}
        cur.execute("SELECT count(*) FROM sends WHERE sent_at::date=%s AND status='sent'", (y,))
        out["sent_yesterday"] = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FILTER (WHERE status='bounced')::float
                       / NULLIF(count(*),0) FROM sends WHERE sent_at::date=%s""", (y,))
        out["bounce_rate"] = round((cur.fetchone()[0] or 0) * 100, 2)
        cur.execute("""SELECT classification, count(*) FROM replies
                       WHERE received_at::date=%s GROUP BY 1 ORDER BY 2 DESC""", (y,))
        out["replies"] = dict(cur.fetchall())
        cur.execute("""SELECT r.full_name, count(*) FROM replies rp
                       JOIN reps r ON r.id=rp.routed_rep_id
                       WHERE NOT rp.handled GROUP BY 1 ORDER BY 2 DESC""")
        out["unhandled_by_rep"] = dict(cur.fetchall())
        # the metric that actually matters: a warm reply nobody answered
        cur.execute("""SELECT count(*) FROM replies
                       WHERE classification IN ('interested','referral')
                         AND NOT handled AND routed_at < now() - interval '4 hours'""")
        out["stale_warm_replies"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM emails WHERE approved IS NULL")
        out["awaiting_approval"] = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM companies WHERE stage='queued'""")
        out["companies_queued"] = cur.fetchone()[0]
        return out
