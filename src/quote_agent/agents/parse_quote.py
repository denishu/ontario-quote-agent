"""Turn a saved quote-result page's text into one or more QuoteObtained --
for a source whose quote lands as an on-page result (confirmed on two
real sites: belairdirect shows a full coverage breakdown alongside the
price; MyChoice, an aggregator, shows several underwriters' prices side
by side with no coverage breakdown at all), not something live
automation reached itself, and never a PDF or other downloadable
artifact.

Decouples the "AI compares quotes" demo story from live-run risk: save
the result page locally once, parse it here, and it feeds through the
exact same build_result()/classify_quote() pipeline a live automated
result would -- same ResultEntry shape, same deterministic coverage
diff, same QuoteON display.

Uses Claude's tool-use for structured extraction, not free-text parsing
-- the model is forced to return values matching a fixed JSON schema, so
a premium or deductible comes back as an actual typed number, not
something regexed out of prose.
"""

import os
from typing import Callable

from anthropic import Anthropic
from dotenv import load_dotenv

from quote_agent.agents.web import QuoteObtained
from quote_agent.models import Confidence, CoverageConfig, Discount

load_dotenv()

_MODEL = "claude-haiku-4-5-20251001"
_MAX_PAGE_CHARS = 8000  # a results page's relevant content, not an unbounded dump

_QUOTE_PROPERTIES = {
    "premium_annual": {"type": "number", "description": "Annual premium in dollars"},
    "premium_monthly": {
        "type": ["number", "null"],
        "description": "Monthly premium in dollars, if shown separately from the annual figure",
    },
    "returned_legal_underwriter": {
        "type": "string",
        "description": (
            "The actual underwriting insurer's name, e.g. 'Wawanesa Mutual' -- NOT a brokerage "
            "or intermediary name (confirmed on a real site, MyChoice: 'Brokered by Hub "
            "International' names the broker, not the insurer actually underwriting the risk)"
        ),
    },
    # Coverage detail fields are genuinely optional, not just permissive --
    # confirmed on a real site (MyChoice) that a comparison-card view can
    # show only price and underwriter with no coverage breakdown at all.
    # Forcing these as required would make the model guess at numbers
    # that simply aren't on the page, which is exactly the fabrication
    # the challenge brief warns against ("reported without inflation or
    # hallucination"). Left null when not shown; extract_quote_from_text
    # falls back to the benchmark for those and marks confidence
    # accordingly rather than claiming an unverified coverage match.
    "third_party_liability_limit": {
        "type": ["integer", "null"],
        "description": "Third-party liability limit in dollars, e.g. 1000000 -- only if actually shown",
    },
    "dcpd_included": {
        "type": ["boolean", "null"],
        "description": "Whether Direct Compensation Property Damage is included -- only if actually shown",
    },
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
}
_QUOTE_REQUIRED = ["premium_annual", "returned_legal_underwriter"]

_EXTRACTION_TOOL = {
    "name": "record_quote",
    "description": "Record the structured details of the one auto insurance quote shown on this results page.",
    "input_schema": {"type": "object", "properties": _QUOTE_PROPERTIES, "required": _QUOTE_REQUIRED},
}

_MULTI_EXTRACTION_TOOL = {
    "name": "record_quotes",
    "description": (
        "Record every distinct insurance quote shown on this aggregator/comparison results "
        "page -- one entry per underwriter, in the order they appear on the page."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "quotes": {
                "type": "array",
                "items": {"type": "object", "properties": _QUOTE_PROPERTIES, "required": _QUOTE_REQUIRED},
            }
        },
        "required": ["quotes"],
    },
}


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=api_key)


def _call_tool(page_text: str, tool: dict, extra_instruction: str = "") -> dict:
    instruction = f"Extract the quote details from this insurance quote result page.{extra_instruction}"
    message = _client().messages.create(
        model=_MODEL,
        max_tokens=2048,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": f"{instruction}\n\n{page_text[:_MAX_PAGE_CHARS]}"}],
    )
    for block in message.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Model did not return a tool_use block")


def _real_llm_extract(page_text: str) -> dict:
    return _call_tool(page_text, _EXTRACTION_TOOL)


_MULTI_EXTRA_INSTRUCTION = (
    " If coverage details (liability limit, deductibles, DCPD, etc.) appear once for the "
    "whole page rather than repeated per quote, they describe one shared coverage "
    "configuration the comparison was run under -- apply them to every quote listed, not "
    "just whichever one happens to appear nearest to them in the text."
)


def _real_llm_extract_multi(page_text: str) -> dict:
    return _call_tool(page_text, _MULTI_EXTRACTION_TOOL, _MULTI_EXTRA_INSTRUCTION)


def _build_quote_obtained(page_text: str, data: dict, benchmark: CoverageConfig) -> QuoteObtained:
    """Shared by extract_quote_from_text and extract_quotes_from_text --
    one extracted quote's raw dict, benchmark-filled where the page
    didn't show something, becomes one QuoteObtained.

    Liability limit, DCPD, and every deductible fall back to the
    benchmark when the page doesn't show them -- these are all things
    the applicant explicitly chose during intake (you pick $1M vs $2M,
    you pick a $500 vs $1000 deductible), so a real quote almost
    certainly honoured what was requested even when a compact comparison
    view doesn't re-display it (confirmed live, MyChoice: none of these
    are shown at all, only price and underwriter). optional_benefits and
    endorsements are different -- genuine product features that vary by
    insurer, not something the applicant chose, so an empty extraction
    for those stays empty rather than being assumed to match the
    benchmark; if the benchmark wanted a specific endorsement and the
    page never confirmed it, that's a real, honest gap worth surfacing
    as a coverage variance, not something to paper over.
    """
    coverage_shown = data.get("third_party_liability_limit") is not None and data.get("dcpd_included") is not None
    coverage = benchmark.model_copy(
        update={
            "third_party_liability_limit": data.get("third_party_liability_limit")
            or benchmark.third_party_liability_limit,
            "dcpd_included": data.get("dcpd_included") if data.get("dcpd_included") is not None else benchmark.dcpd_included,
            "dcpd_deductible": data.get("dcpd_deductible") if data.get("dcpd_deductible") is not None else benchmark.dcpd_deductible,
            "collision_deductible": data.get("collision_deductible")
            if data.get("collision_deductible") is not None
            else benchmark.collision_deductible,
            "comprehensive_deductible": data.get("comprehensive_deductible")
            if data.get("comprehensive_deductible") is not None
            else benchmark.comprehensive_deductible,
            "all_perils_deductible": data.get("all_perils_deductible")
            if data.get("all_perils_deductible") is not None
            else benchmark.all_perils_deductible,
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
        # medium, not high, when coverage was assumed from the benchmark
        # rather than confirmed on the page itself -- an exact premium
        # was still returned, but "matching coverage" per the Confidence
        # rubric isn't independently verified in that case.
        confidence=Confidence.HIGH if coverage_shown else Confidence.MEDIUM,
    )


def extract_quote_from_text(
    page_text: str,
    benchmark: CoverageConfig,
    *,
    llm_extract: Callable[[str], dict] | None = None,
) -> QuoteObtained:
    """Parse a saved single-quote results page's text into a QuoteObtained.

    benchmark supplies whatever the returned quote doesn't restate on its
    own -- a real quote confirms the terms actually requested rather than
    re-displaying every one of them, so assuming the site honoured what
    was asked for is the honest default for fields the page genuinely
    doesn't show (see _build_quote_obtained for exactly which fields and
    how confidence reflects that).

    llm_extract, when given, replaces the real Anthropic call -- same
    injected-dependency shape as resolve_field's llm_fallback and
    summarize_outcome, so tests never need network access or an API key.
    """
    extract = llm_extract or _real_llm_extract
    data = extract(page_text)
    return _build_quote_obtained(page_text, data, benchmark)


def extract_quotes_from_text(
    page_text: str,
    benchmark: CoverageConfig,
    *,
    llm_extract: Callable[[str], dict] | None = None,
) -> list[QuoteObtained]:
    """Parse a saved aggregator/comparison results page showing several
    underwriters' quotes at once into one QuoteObtained per underwriter.

    Confirmed on a real site (MyChoice): a comparison-card view can list
    several distinct quotes on one page with no per-quote coverage
    breakdown at all -- see _build_quote_obtained for how that's handled
    (benchmark fallback, confidence downgrade), applied identically to
    every quote here.

    llm_extract, when given, replaces the real Anthropic call and should
    return the same shape record_quotes' tool schema does (a dict with a
    "quotes" list) -- same injected-dependency shape used throughout this
    codebase, so tests never need network access or an API key.
    """
    extract = llm_extract or _real_llm_extract_multi
    data = extract(page_text)
    return [_build_quote_obtained(page_text, quote, benchmark) for quote in data["quotes"]]
