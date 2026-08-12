"""Turn a saved quote-result page's text into a QuoteObtained -- for a
source whose quote lands as an on-page result (confirmed on a real site,
belairdirect: price plus a coverage breakdown, no PDF or other
downloadable artifact), not something live automation reached itself.

Decouples the "AI compares quotes" demo story from live-run risk: save
the result page locally once, parse it here, and it feeds through the
exact same build_result()/classify_quote() pipeline a live automated
result would -- same ResultEntry shape, same deterministic coverage
diff, same QuoteON display.

Uses Claude's tool-use for structured extraction, not free-text parsing
-- the model is forced to return values matching a fixed JSON schema
(record_quote's input_schema below), so a premium or deductible comes
back as an actual typed number, not something regexed out of prose.
"""

import os
from typing import Callable

from anthropic import Anthropic
from dotenv import load_dotenv

from quote_agent.agents.web import QuoteObtained
from quote_agent.models import CoverageConfig, Discount

load_dotenv()

_MODEL = "claude-haiku-4-5-20251001"
_MAX_PAGE_CHARS = 8000  # a results page's relevant content, not an unbounded dump

_EXTRACTION_TOOL = {
    "name": "record_quote",
    "description": "Record the structured details of an auto insurance quote shown on a results page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "premium_annual": {"type": "number", "description": "Annual premium in dollars"},
            "premium_monthly": {
                "type": ["number", "null"],
                "description": "Monthly premium in dollars, if shown separately from the annual figure",
            },
            "returned_legal_underwriter": {
                "type": "string",
                "description": "The insurer/underwriter name actually shown on the page",
            },
            "third_party_liability_limit": {
                "type": "integer",
                "description": "Third-party liability limit in dollars, e.g. 1000000 or 2000000",
            },
            "dcpd_included": {"type": "boolean", "description": "Whether Direct Compensation Property Damage is included"},
            "dcpd_deductible": {"type": ["number", "null"]},
            "collision_deductible": {"type": ["number", "null"]},
            "comprehensive_deductible": {"type": ["number", "null"]},
            "all_perils_deductible": {"type": ["number", "null"]},
            "optional_benefits": {
                "type": "object",
                "description": (
                    "Map of optional benefit name (as shown on the page) to its status, for "
                    "whatever benefits are actually visible -- do not invent ones that aren't shown"
                ),
                "additionalProperties": {"type": "string", "enum": ["included", "excluded", "unavailable", "unknown"]},
            },
            "endorsements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Named endorsements shown on the page, e.g. 'OPCF 44R'",
            },
            "discounts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "applied": {"type": "boolean"}},
                    "required": ["name", "applied"],
                },
            },
        },
        "required": ["premium_annual", "returned_legal_underwriter", "third_party_liability_limit", "dcpd_included"],
    },
}


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=api_key)


def _real_llm_extract(page_text: str) -> dict:
    message = _client().messages.create(
        model=_MODEL,
        max_tokens=1024,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_quote"},
        messages=[
            {
                "role": "user",
                "content": f"Extract the quote details from this insurance quote result page:\n\n{page_text[:_MAX_PAGE_CHARS]}",
            }
        ],
    )
    for block in message.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Model did not return a tool_use block")


def extract_quote_from_text(
    page_text: str,
    benchmark: CoverageConfig,
    *,
    llm_extract: Callable[[str], dict] | None = None,
) -> QuoteObtained:
    """Parse a saved quote-result page's text into a QuoteObtained.

    benchmark supplies whatever the returned quote doesn't restate on its
    own (effective_date, term_months, accident_benefits_mandatory,
    uninsured_automobile_included, telematics_opt_in) -- a real quote
    confirms the terms actually requested rather than re-displaying every
    one of them, so assuming the site honoured what was asked for is the
    honest default for fields the page genuinely doesn't show. Everything
    the page does show (premium, liability limit, deductibles, DCPD,
    optional benefits, endorsements, discounts) comes from the extraction
    itself, not the benchmark.

    llm_extract, when given, replaces the real Anthropic call -- same
    injected-dependency shape as resolve_field's llm_fallback and
    summarize_outcome, so tests never need network access or an API key.
    """
    extract = llm_extract or _real_llm_extract
    data = extract(page_text)

    coverage = benchmark.model_copy(
        update={
            "third_party_liability_limit": data["third_party_liability_limit"],
            "dcpd_included": data["dcpd_included"],
            "dcpd_deductible": data.get("dcpd_deductible"),
            "collision_deductible": data.get("collision_deductible"),
            "comprehensive_deductible": data.get("comprehensive_deductible"),
            "all_perils_deductible": data.get("all_perils_deductible"),
            "optional_benefits": data.get("optional_benefits") or {},
            "endorsements": data.get("endorsements") or [],
        }
    )

    discounts = [Discount(name=d["name"], applied=d["applied"]) for d in data.get("discounts") or []]

    return QuoteObtained(
        raw_evidence_text=page_text,
        premium_annual=data["premium_annual"],
        returned_coverage=coverage,
        returned_legal_underwriter=data["returned_legal_underwriter"],
        discounts=discounts,
    )
