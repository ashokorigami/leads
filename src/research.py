"""Opus 5 research + scoring.

Stable prefix (ORIGAMI + RUBRIC) is prompt-cached, so repeat calls read it at
~0.1x. Only the company block varies.
"""
import json
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from config import ANTHROPIC_KEY, MODEL_RESEARCH
from origami_context import ORIGAMI, RUBRIC
import llm
import company_profile

_client = Anthropic(api_key=ANTHROPIC_KEY)

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "0-100. Below 70 means do not send."},
        "wedge": {"type": "string", "enum": [
            "doc_intelligence", "auctions", "gaming", "mobile",
            "commerce", "ai_product", "dedicated_team", "none"]},
        "primary_trigger": {"type": "string",
            "description": "The single checkable fact the email will open on. "
                           "Must be quotable verbatim to the recipient."},
        "angle": {"type": "string",
            "description": "One sentence: why Origami is relevant to THEM, now. "
                           "NEVER name the company's cloud, ERP or document "
                           "system unless that exact product appears in the "
                           "evidence you were given - say 'their own cloud'. "
                           "Anything you write here can reach the reader."},
        "proof_ref": {"type": "string",
            "description": "Which proof to cite. Must respect NDA and "
                           "attribution warnings. 'none' if nothing fits."},
        "evidence_quote": {"type": "string",
            "description": "VERBATIM span, 12-200 characters, copied EXACTLY "
                           "from the company's own text supplied below. This is "
                           "checked against the stored source: if it does not "
                           "appear there word for word, the whole result is "
                           "thrown away. Never paraphrase, never write from "
                           "memory. Empty string only if you are disqualifying "
                           "or the only evidence is a job posting."},
        "disqualify_reason": {"type": ["string", "null"]},
        "reasoning": {"type": "string", "description": "Two sentences max."},
    },
    "required": ["score", "wedge", "primary_trigger", "angle", "proof_ref",
                 "evidence_quote", "disqualify_reason", "reasoning"],
    "additionalProperties": False,
}


def _sources_block(pages: list[dict]) -> str:
    if not pages:
        return "\n# The company's own words\n(none retrieved)\n"
    out = ["\n# The company's own words - QUOTE ONLY FROM HERE"]
    for p in pages[:3]:
        out.append(f"\n--- {p['url']} ---\n{p['text'][:6000]}")
    return "\n".join(out)


def _company_block(org: dict, triggers: list[dict]) -> str:
    tech = (org.get("technology_names") or [])[:40]
    return f"""
# Company
name        : {org.get('name')}
domain      : {org.get('primary_domain') or org.get('website_url')}
industry    : {org.get('industry')}
employees   : {org.get('estimated_num_employees')}
founded     : {org.get('founded_year')}
country     : {(org.get('organization_city') or '')} {(org.get('country') or '')}
description : {(org.get('short_description') or '')[:600]}
keywords    : {', '.join((org.get('keywords') or [])[:25])}
technologies: {', '.join(tech)}
funding     : {org.get('total_funding_printed')} | latest {org.get('latest_funding_stage')} {str(org.get('latest_funding_round_date'))[:10]}

# Observed signals (may be empty - absence is NOT a disqualification)
""" + ("\n".join(f"- [{t['kind']}] {t['detail']}" for t in triggers)
       or "(none - judge this company on what it says about itself)")


@retry(stop=stop_after_attempt(3),
       wait=wait_exponential_jitter(initial=3, max=30))
def research(org: dict, triggers: list[dict], pages: list[dict] | None = None) -> dict:
    pages = pages or []
    prompt = _company_block(org, triggers) + _sources_block(pages)
    r, used = llm.call(
        llm.RESEARCH_CHAIN,
        max_tokens=2000,
        system=[{"type": "text", "text": ORIGAMI + RUBRIC,
                 "cache_control": {"type": "ephemeral"}}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA},
                       "effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in r.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError(
            f"model returned no text block (stop_reason={r.stop_reason})")
    try:
        out = json.loads(text)
    except json.JSONDecodeError as ex:
        raise RuntimeError(f"model returned non-JSON ({ex}): {text[:160]}") from None

    # The deterministic half of the gate. The model must QUOTE, and the quote
    # must genuinely appear in text we fetched and stored. A remembered fact
    # cannot pass - which is exactly how "your Azure tenancy" got through on
    # 2026-08-01, when the check trusted a model-written field as evidence.
    out["evidence_url"] = None
    q = (out.get("evidence_quote") or "").strip()
    if q and pages:
        url = company_profile.quote_is_real(q, pages)
        out["evidence_url"] = url
        if url is None:
            out["quote_unverified"] = q
            # Not fatal on its own: a company with a real hiring trigger can
            # still qualify. But it may never become the opening fact.
            out["evidence_quote"] = ""
    out["_model"] = used
    out["_usage"] = {
        "in": r.usage.input_tokens, "out": r.usage.output_tokens,
        "cache_read": getattr(r.usage, "cache_read_input_tokens", 0),
        "cache_write": getattr(r.usage, "cache_creation_input_tokens", 0),
    }
    return out
