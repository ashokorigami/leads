"""Classify inbound replies and route them to a rep.

The expensive failure in outbound is not a bad email - it is a warm reply
nobody answers for three days. So classification exists to get the right
human onto the right message fast, and to stop the sequence dead the moment
someone responds.
"""
import json
from anthropic import Anthropic
from config import ANTHROPIC_KEY, MODEL_RESEARCH, db

_client = Anthropic(api_key=ANTHROPIC_KEY)

RULES = """
You triage replies to a cold email from Origami, a software consultancy.

Classify into exactly one:
  interested      - wants to talk, asks a question, requests info or a call
  not_now         - open in principle, wrong timing ("revisit in Q1", "not this year")
  referral        - points at a different person or team
  not_interested  - a clear no, but civil
  unsubscribe     - asks to stop, or is annoyed. Treat ANY irritation as this.
  ooo             - automatic out-of-office
  auto            - other automated mail: ticketing, no-reply, delivery receipts
  bounce          - mailbox does not exist, delivery failure

Rules that matter:
- If a human wrote it and there is ANY hint of annoyance, classify unsubscribe.
  A complaint costs domain reputation; a missed lead costs one lead.
- referral: put the named person or team in extracted_contact.
- not_now: put any stated timing in follow_up_hint.
- urgency 1-5. A direct question or a request to talk is 5.
- Never guess at intent that is not in the text.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum":
            ["interested","not_now","referral","not_interested",
             "unsubscribe","ooo","auto","bounce"]},
        "confidence": {"type": "number", "description": "0.0 to 1.0"},
        "urgency": {"type": "integer", "description": "1 to 5"},
        "summary": {"type": "string", "description": "One sentence for the rep."},
        "extracted_contact": {"type": ["string","null"]},
        "follow_up_hint": {"type": ["string","null"]},
        "suggested_reply": {"type": ["string","null"],
            "description": "Draft reply if interested or referral, else null. "
                            "Under 60 words, plain, no marketing language."},
    },
    "required": ["classification","confidence","urgency","summary",
                 "extracted_contact","follow_up_hint","suggested_reply"],
    "additionalProperties": False,
}


def classify(from_email: str, subject: str, body: str, context: str = "") -> dict:
    r = _client.messages.create(
        model=MODEL_RESEARCH, max_tokens=1200,
        system=[{"type":"text","text":RULES,"cache_control":{"type":"ephemeral"}}],
        output_config={"format":{"type":"json_schema","schema":SCHEMA}},
        messages=[{"role":"user","content":
            f"From: {from_email}\nSubject: {subject}\n\n{body}\n\n{context}"}],
    )
    return json.loads(next(b.text for b in r.content if b.type == "text"))


def next_rep(cur) -> tuple[int, str]:
    """Round-robin by who is holding the fewest unhandled replies - keeps load
    even rather than merely alternating."""
    cur.execute("""
        SELECT r.id, r.full_name, count(rp.id) FILTER (WHERE NOT rp.handled) AS open
        FROM reps r LEFT JOIN replies rp ON rp.routed_rep_id = r.id
        WHERE r.active GROUP BY r.id, r.full_name
        ORDER BY open ASC, r.id ASC LIMIT 1""")
    row = cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


def ingest(from_email: str, subject: str, body: str, received_at,
           prospect_id: int | None = None, send_id: int | None = None) -> dict:
    """Classify, route, suppress if needed, and stop the sequence."""
    c = classify(from_email, subject, body)
    with db() as conn, conn.cursor() as cur:
        rep_id, rep_name = (None, None)
        if c["classification"] in ("interested","not_now","referral"):
            rep_id, rep_name = next_rep(cur)

        cur.execute("""INSERT INTO replies (prospect_id, send_id, from_email, subject,
                       body, received_at, classification, confidence, routed_rep_id,
                       routed_at, raw)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,
                               CASE WHEN %s IS NULL THEN NULL ELSE now() END, %s)
                       RETURNING id""",
                    (prospect_id, send_id, from_email, subject, body, received_at,
                     c["classification"], c["confidence"], rep_id, rep_id,
                     json.dumps(c)))
        rid = cur.fetchone()[0]

        # anyone who opts out or complains never gets contacted again
        if c["classification"] in ("unsubscribe","not_interested"):
            cur.execute("""INSERT INTO suppression (kind,value,reason)
                           VALUES ('email',%s,%s)
                           ON CONFLICT (kind,value) DO NOTHING""",
                        (from_email.lower(), c["classification"]))
    c["_reply_id"], c["_rep"] = rid, rep_name
    return c
