"""A best-effort WebFlow for any registry entry with no dedicated
site-specific implementation: navigate to entry.quote_url and run the
fully generic fill loop (fill_visible_fields + run_flow_steps), with no
knowledge of that site's particular quirks at all.

This exists so every registry entry can be attempted -- and get an
honest, evidence-backed terminal status -- even before someone sits down
and maps that specific site the way onlia.py maps Onlia. It will
routinely underperform a real site-specific flow (get stuck on a widget
detect_widget_type can't classify, a CAPTCHA, a login wall, whatever) --
that's expected, not a bug: it exists to establish a floor of coverage
across the whole registry, not to replace real per-site mapping.

Uses the LLM fallback (llm_resolve_field), not just the hardcoded alias
table -- the alias table was seeded entirely from ThinkInsure and Onlia's
actual labels, so on any other, never-mapped site it would otherwise
discover fields but fail to resolve almost all of them. The LLM fallback
is the whole reason resolve_field() has a two-tier design in the first
place: this is exactly the "genuinely novel phrasing" case it exists for.
"""

from playwright.sync_api import sync_playwright

from quote_agent.agents.flow import run_flow_steps
from quote_agent.agents.web import NonQuoteOutcome, QuoteObtained, WebFlow
from quote_agent.mapping.llm_fallback import llm_resolve_field
from quote_agent.models import IntakeProfile, RegistryEntry
from quote_agent.models.status import QuoteStatus


def make_generic_flow(entry: RegistryEntry) -> WebFlow:
    """Build a WebFlow closed over one registry entry's quote_url. A
    factory rather than a flow taking (entry, intake) directly, so the
    result still matches the plain WebFlow signature run_web_attempt
    expects: Callable[[IntakeProfile], QuoteObtained | NonQuoteOutcome].
    """
    if entry.quote_url is None:
        raise ValueError(f"{entry.registry_id} has no quote_url to navigate to")
    quote_url = entry.quote_url

    def flow(intake: IntakeProfile) -> QuoteObtained | NonQuoteOutcome:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(quote_url, timeout=60000)
                result = run_flow_steps(page, intake, llm_fallback=llm_resolve_field)
                last_step = result.steps[-1] if result.steps else None
                return NonQuoteOutcome(
                    status=QuoteStatus.UNRESOLVED,
                    raw_evidence_text=page.inner_text("body"),
                    failure_reason=(
                        "Generic best-effort attempt only -- no site-specific handling implemented. "
                        f"Filled: {sorted(last_step.fill_report.filled) if last_step else []}; "
                        f"unresolved: {sorted(last_step.fill_report.unresolved) if last_step else []}; "
                        f"unknown widgets: {sorted(last_step.fill_report.skipped_unknown_widget) if last_step else []}"
                    ),
                    next_action="Needs a dedicated site-specific flow (see agents/sites/) to progress further",
                )
            finally:
                browser.close()

    return flow
