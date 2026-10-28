"""Model call with a fallback chain.

An Anthropic incident on 2026-07-30 knocked out Opus 5 for roughly half an hour
and silently cost two prospects. Retrying the same model does not help when that
model is the thing that is down, so try the next one instead. All three accept an
identical request shape here (no `thinking` param, `output_config` supported), so
a fallback is a model-string swap and nothing else.

2026-10-28: the Anthropic key went invalid (401 on every model) and stopped the
re-research. OUTBOUND_LLM=local routes both chains to gpt-oss-120b served by vLLM
on the Blackwell box (gex131), reached through an SSH tunnel on LOCAL_LLM_URL.
Chain entries prefixed "local:" go there; the response is wrapped to look like
an Anthropic Message so research.py / write.py need no change.
"""
import os
from types import SimpleNamespace

import httpx
from anthropic import Anthropic
from config import ANTHROPIC_KEY

_client = Anthropic(api_key=ANTHROPIC_KEY)

LOCAL_URL = os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8001/v1")
LOCAL_REASONING = os.environ.get("LOCAL_LLM_REASONING", "high")

# Order matters: best judgement first, then a different family so a single
# model's outage cannot stop the pipeline.
if os.environ.get("OUTBOUND_LLM") == "local":
    RESEARCH_CHAIN = ["local:gpt-oss-120b"]
    WRITE_CHAIN    = ["local:gpt-oss-120b"]
else:
    RESEARCH_CHAIN = ["claude-opus-5", "claude-opus-4-8", "claude-fable-5"]
    WRITE_CHAIN    = ["claude-fable-5", "claude-opus-5", "claude-opus-4-8"]


def _text(content) -> str:
    """Anthropic content (str or list of blocks) -> plain text."""
    if isinstance(content, str):
        return content
    return "\n\n".join(b.get("text", "") for b in content if b.get("type") == "text")


LOCAL_QUOTE_RULE = """

# Quoting rule (strict)
Any field that asks for a quote must be ONE contiguous span copied
character-for-character from a single source text above: same language, same
spelling, same punctuation. No ellipsis, no added quotation marks, no
translation, no joining two passages, no summarising. 12-200 characters. If no
span supports the point, leave the quote empty rather than paraphrase.
"""


def _local(model: str, system=None, messages=(), max_tokens=2000,
           output_config=None, **_ignored) -> SimpleNamespace:
    msgs = []
    if system:
        # gpt-oss paraphrases where Opus copies: 0 of 5 evidence quotes passed
        # company_profile.quote_is_real() on 2026-10-28, vs 1,301 of 1,309 for Opus.
        msgs.append({"role": "system", "content": _text(system) + LOCAL_QUOTE_RULE})
    msgs += [{"role": m["role"], "content": _text(m["content"])} for m in messages]
    body = {
        "model": model,
        "messages": msgs,
        # gpt-oss reasons before it answers and the reasoning counts against
        # max_tokens; the Anthropic budgets here were sized for the answer only.
        "max_tokens": max(max_tokens * 4, 8000),
        "reasoning_effort": LOCAL_REASONING,
    }
    fmt = (output_config or {}).get("format")
    if fmt and fmt.get("type") == "json_schema":
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "out", "schema": fmt["schema"]}}
    r = httpx.post(f"{LOCAL_URL}/chat/completions", json=body, timeout=600)
    r.raise_for_status()
    d = r.json()
    ch = d["choices"][0]
    text = ch["message"].get("content")
    u = d.get("usage") or {}
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)] if text else [],
        stop_reason=ch.get("finish_reason"),
        usage=SimpleNamespace(input_tokens=u.get("prompt_tokens"),
                              output_tokens=u.get("completion_tokens"),
                              cache_read_input_tokens=0,
                              cache_creation_input_tokens=0),
    )


def call(chain: list[str], **kw) -> tuple[object, str]:
    """Try each model in turn. Returns (response, model_used)."""
    last = None
    for model in chain:
        try:
            if model.startswith("local:"):
                r = _local(model.split(":", 1)[1], **kw)
            else:
                r = _client.messages.create(model=model, **kw)
            text = next((b.text for b in r.content if b.type == "text"), None)
            if text is None:
                raise RuntimeError(f"no text block (stop_reason={r.stop_reason})")
            return r, model
        except Exception as e:
            last = e
            continue
    raise RuntimeError(f"all models failed, last error: {last}") from None
