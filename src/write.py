"""Fable 5 writes the email. Short input, short output - the premium model is
cheap here, and this is the one thing that decides reply rate."""
import json
import re
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from config import ANTHROPIC_KEY, MODEL_WRITE
from origami_context import ORIGAMI
import llm

_client = Anthropic(api_key=ANTHROPIC_KEY)

# Naming a PROSPECT's technology is only permitted when we actually observed it.
# Caught live on 2026-08-01: the writer told Boskalis, Van Oord and Clayco the
# platform "sets up in your Azure tenancy" and Kuehne+Nagel "your own AWS
# tenancy" - pure invention, because the capability library lists "Azure and
# AWS" as ORIGAMI's stack and the model read that as a menu to assign.
#
# A prompt rule alone drifts back. This gate is deterministic: a technology may
# appear only if its name is in the evidence we gathered (the trigger text, e.g.
# a real "AWS Platform Engineer" job title). Everything else is rejected and
# rewritten.
TECH = re.compile(
    r"\b(AWS|Azure|GCP|Google Cloud|SharePoint|Databricks|Snowflake|SAP|"
    r"Salesforce|ServiceNow|Workday|Oracle|Kubernetes|Copilot|OpenAI|"
    r"Sitecore|Documentum|OpenText)\b", re.I)


def unverified_tech(body: str, evidence: str) -> list[str]:
    """Technology names in the email that are not in what we observed."""
    ev = (evidence or "").lower()
    return sorted({m.group(0) for m in TECH.finditer(body or "")
                   if m.group(0).lower() not in ev})

RULES = """
You write one cold email for Origami. It goes to a real person who did not ask
to hear from you. Earn the reply.

# Non-negotiable
- Open on the SPECIFIC FACT in primary_trigger. Name it. They must recognise it
  as true about them in the first sentence.
- 70-110 words in the body. Not one word more.
- Plain text. No markdown, no bullets, no bold, no emoji, no links.
- One ask, and make it small: a reply, not a 30-minute call.
- Respect every guardrail in the capability library: never name the NDA client,
  never imply Origami worked for another company's brand partners.

# Never assert what you cannot know about a job posting
We know an ad is STILL LISTED. We do NOT know it is unfilled - plenty of ads are
left up after a hire. So write "still listed", "still open on your careers page",
"has been posted since May" - never "unfilled for 74 days" or "you have not
filled this". And give them a graceful out in the same breath, e.g. "if that has
been filled, ignore me - the underlying problem usually outlives the hire".
Being wrong about their hiring in sentence one loses the reader permanently.

# Never assert what you cannot know about their technology
You do NOT know what cloud, database, ERP or document system the reader runs.
Never write "your Azure tenancy", "your AWS account", "your SharePoint" or any
other named product in the second person. The capability library lists Azure and
AWS because ORIGAMI works in both - that is OUR stack, never an assumption about
THEIRS. Write "your own cloud", "your own environment" or "inside your own
tenancy" instead: true whoever they run, and it still makes the point that the
data never leaves their control. The only exception is a technology named in the
trigger itself - if their advert is for an "AWS Platform Engineer" you may say so,
because you observed it.

# Never write
- "I hope this finds you well", "I wanted to reach out", "quick question"
- "revolutionise", "cutting-edge", "seamless", "leverage", "solutions"
- Flattery about their company. Any sentence that could be sent to anyone else.
- Fake familiarity, fake urgency, fake deadlines.
- A subject line in title case or with a colon. Lowercase, 2-5 words, concrete.

# Shape
Sentence 1 : the fact, stated plainly.
Sentence 2 : what it usually means, from experience - not a guess about them.
Sentence 3 : the one relevant thing Origami has built, with a real number.
Sentence 4 : the ask. Small - and leave the door open to a DIFFERENT need.
             Origami builds far more than the one thing this email pitches, and
             the reader may be carrying an entirely different problem. So the
             closing question should invite that without listing capabilities.
             Something in the spirit of "...even if the thing on your list this
             year is something else entirely?" - vary the wording, never append
             a menu of services. One clause, not a sentence about what we do.
Then the signature block exactly as given - including the postal address and
the opt-out line. Both are required: the address by CAN-SPAM, the opt-out
because a reader who opts out instead of hitting "spam" protects the sending
domain. Never omit, reword or reformat either.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "lowercase, 2-5 words"},
        "body": {"type": "string", "description": "70-110 words + signature"},
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential_jitter(initial=3, max=30))
def write(org: dict, r: dict, first_name: str, title: str, rep: dict) -> dict:
    brief = f"""
recipient   : {first_name}, {title} at {org.get('name')}
trigger     : {r['primary_trigger']}
angle       : {r['angle']}
proof to use: {r['proof_ref']}
wedge       : {r['wedge']}

signature block to use VERBATIM, exactly as written, nothing added or removed:
{rep['full_name']}
Origami Consulting LLC
641 Lexington Avenue, 14th Floor, New York, NY 10022, US
origami.dev | +1 (450) 212-9365

Not relevant? Reply "no" and I won't write again.
"""
    # OBSERVED evidence only - primary_trigger is built from real Apollo job
    # postings. `angle` and `proof_ref` are MODEL OUTPUT and must never count as
    # evidence: on 2026-08-01 the scorer itself invented "deploys inside
    # Boskalis' own Azure tenancy", and an evidence set that included `angle`
    # waved it straight through. A check that trusts the thing it is checking
    # is not a check.
    evidence = str(r.get("primary_trigger") or "")

    messages = [{"role": "user", "content": brief}]
    for attempt in range(3):
        resp, used = llm.call(
            llm.WRITE_CHAIN, max_tokens=1500,
            system=[{"type": "text", "text": ORIGAMI + RULES,
                     "cache_control": {"type": "ephemeral"}}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            messages=messages,
        )
        _t = next((b.text for b in resp.content if b.type == "text"), None)
        if _t is None:
            raise RuntimeError(
                f"model returned no text block (stop_reason={resp.stop_reason})")
        try:
            out = json.loads(_t)
        except json.JSONDecodeError as ex:
            raise RuntimeError(f"model returned non-JSON ({ex}): {_t[:160]}") from None

        bad = unverified_tech(out.get("body", ""), evidence)
        if not bad:
            break

        messages += [
            {"role": "assistant", "content": _t},
            {"role": "user", "content":
                f"You named {', '.join(bad)}. We have no evidence this company "
                f"uses that, and being wrong about the reader's own stack loses "
                f"the reply. Rewrite with no named technology - say 'your own "
                f"cloud' or 'your own environment' instead. Change nothing else."},
        ]
    else:
        raise RuntimeError(
            f"writer kept asserting unverified technology {bad} after 3 attempts")

    out["_model"] = used
    out["_usage"] = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}
    out["_rewrites"] = attempt
    return out
