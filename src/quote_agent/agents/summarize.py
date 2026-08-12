"""LLM-generated one-line summaries of a non-quote outcome, from the raw
evidence text a flow actually captured at the point it stopped.

Kept separate from web.py so build_result()/run_web_attempt() never
require network access or an API key by default -- summarize is an
injected, optional dependency there, same shape as resolve_field()'s
llm_fallback. Without it, a NonQuoteOutcome's own failure_reason (still
required on the dataclass, still hand-written by whoever writes the
flow) is used as-is; with it, that hand-written string is replaced by
one grounded in the actual evidence.

Uses Haiku, not Sonnet -- summarizing a short evidence snippet into one
sentence doesn't need deeper reasoning, matching the same cost tradeoff
already made for llm_resolve_field.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

from quote_agent.models.status import QuoteStatus

load_dotenv()

_MODEL = "claude-haiku-4-5-20251001"
_MAX_EVIDENCE_CHARS = 4000  # a snippet, not a full-page dump -- controls token cost

_SYSTEM_PROMPT = (
    "You summarize why an automated insurance-quote attempt stopped where "
    "it did, for display as a single line on a status dashboard. You are "
    "given the attempt's final status and the raw page text captured at "
    "the point it stopped (already redacted of personal data). Describe "
    "concretely what the evidence actually shows -- not a generic "
    "description of the status category, and not speculation about "
    "anything not shown in the evidence. One sentence, no more than 25 "
    "words. Respond with only that sentence -- no preamble, no quotes "
    "around it, nothing else."
)


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=api_key)


def summarize_outcome(status: QuoteStatus, raw_evidence_text: str) -> str:
    """Ask Claude for a one-line, evidence-grounded summary of why a
    non-quote outcome stopped where it did. Only the first line of the
    response is used, in case the model adds anything after the sentence
    despite the prompt -- same defensive parsing as llm_resolve_field.
    """
    snippet = raw_evidence_text[:_MAX_EVIDENCE_CHARS]
    message = _client().messages.create(
        model=_MODEL,
        max_tokens=100,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Status: {status.value}\n\nEvidence:\n{snippet}",
            }
        ],
    )
    return message.content[0].text.strip().splitlines()[0].strip()
