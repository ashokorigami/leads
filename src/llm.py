"""Model call with a fallback chain.

An Anthropic incident on 2026-07-30 knocked out Opus 5 for roughly half an hour
and silently cost two prospects. Retrying the same model does not help when that
model is the thing that is down, so try the next one instead. All three accept an
identical request shape here (no `thinking` param, `output_config` supported), so
a fallback is a model-string swap and nothing else.
"""
from anthropic import Anthropic
from config import ANTHROPIC_KEY

_client = Anthropic(api_key=ANTHROPIC_KEY)

# Order matters: best judgement first, then a different family so a single
# model's outage cannot stop the pipeline.
RESEARCH_CHAIN = ["claude-opus-5", "claude-opus-4-8", "claude-fable-5"]
WRITE_CHAIN    = ["claude-fable-5", "claude-opus-5", "claude-opus-4-8"]


def call(chain: list[str], **kw) -> tuple[object, str]:
    """Try each model in turn. Returns (response, model_used)."""
    last = None
    for model in chain:
        try:
            r = _client.messages.create(model=model, **kw)
            text = next((b.text for b in r.content if b.type == "text"), None)
            if text is None:
                raise RuntimeError(f"no text block (stop_reason={r.stop_reason})")
            return r, model
        except Exception as e:
            last = e
            continue
    raise RuntimeError(f"all models failed, last error: {last}") from None
