"""Aviva's vehicle-details step (myaviva.avivainsurance.ca/avivaquoter/
bol/auto/vehicle) -- the only part of Aviva's flow mapped and validated
against the real live site so far. Fills postal code, year, make, model,
purchase month/year, vehicle condition, anti-theft device, and winter
tires automatically, using the fully generic fill loop (fill_visible_fields
+ run_flow_steps) plus one Aviva-specific step: dismissing a modal that
never closes on its own.

Unlike Onlia, Aviva's real quoter URL isn't stable/reusable -- it carries
a sid= session token that's freshly minted each time a real visitor
clicks "Get a Quote" on Aviva's marketing site (aviva.ca), and confirmed
to stop working once stale (a fresh request to an old one returns
Akamai's "Access Denied" edge block, not the form). This flow doesn't yet
automate obtaining that fresh URL itself -- the caller supplies a current
one. A factory (make_aviva_flow) rather than a fixed FORM_URL constant,
for exactly this reason -- see agents.generic_flow for the same pattern
applied to any registry entry.

Confirmed live: the postal code modal that gates the page never actually
dismisses itself -- it stays open (style="display: block") even once
filled, silently blocking every later .click()-based interaction (radio/
checkbox) elsewhere on the page behind it, while select_option() calls on
<select> fields succeed regardless, since those don't check visual
occlusion the way a real click does. Explicitly clicking the modal's own
Continue button fixes this -- confirmed live, everything past it (make,
model, purchase date, vehicle condition, anti-theft device) then fills
correctly through the fully generic pipeline with no further Aviva-
specific handling needed.

This flow was validated through the end of the vehicle-details page (it
advances to whatever comes next), but that next page is itself unmapped
-- always ends in MANUAL_HANDOFF, not because of a safety boundary the
way Onlia's consent checkpoint is, but simply because nothing past this
point has been explored or tested yet.

Deliberately not covered by the pytest suite: this launches a real
browser against a real live third-party site every time it runs, which
isn't something to run repeatedly/automatically in CI. Validated instead
by direct, repeated runs against the live page during development (see
commit history) -- the underlying primitives it calls (fill_visible_fields,
run_flow_steps, select_native, discover_fields) all have full local
fixture coverage of their own.
"""

from playwright.sync_api import sync_playwright

from quote_agent.agents.flow import run_flow_steps
from quote_agent.agents.web import NonQuoteOutcome, QuoteObtained, WebFlow
from quote_agent.mapping.llm_fallback import llm_resolve_field
from quote_agent.models import IntakeProfile
from quote_agent.models.status import QuoteStatus

_MAX_STEPS = 30


def make_aviva_flow(start_url: str, *, headless: bool = True) -> WebFlow:
    """Build a WebFlow for Aviva's vehicle-details step, closed over a
    specific starting URL. start_url must be a fresh myaviva.avivainsurance.ca
    link (obtained by clicking "Get a Quote" on aviva.ca) -- see module
    docstring for why this can't be a fixed constant the way Onlia's is.

    headless defaults to True; confirmed live that Aviva's own edge/WAF
    layer (Akamai) can genuinely block a fresh headless request the same
    way Onlia's reCAPTCHA does, so this stays an explicit opt-in a caller
    makes on their own real desktop session, not a silent default chosen
    because it happens to dodge the block.

    CaptchaDetected (from fill_visible_fields, now also covering generic
    edge/WAF access-denied pages) and StopBeforeSensitiveAction (from
    run_flow_steps, when not headless) both propagate to the caller
    rather than being caught here -- run_web_attempt is what turns those
    into the right terminal status.
    """

    def flow(intake: IntakeProfile) -> QuoteObtained | NonQuoteOutcome:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            page = browser.new_page()
            try:
                page.goto(start_url, timeout=60000)
                page.wait_for_selector("#postalCode", timeout=30000)

                postal_field = page.locator("#postalCode")
                if postal_field.count() > 0 and postal_field.is_visible():
                    postal_field.fill(intake.address.postal_code)
                    page.locator('modal-container button[type="submit"]').click()
                    page.wait_for_timeout(1000)

                run_flow_steps(
                    page,
                    intake,
                    max_steps=_MAX_STEPS,
                    llm_fallback=llm_resolve_field,
                    interactive=not headless,
                )

                return NonQuoteOutcome(
                    status=QuoteStatus.MANUAL_HANDOFF,
                    raw_evidence_text=page.inner_text("body"),
                    failure_reason=(
                        "Vehicle-details step (page 1) completed as far as this flow is mapped. "
                        "Whatever page comes next is unmapped -- this flow was never exercised "
                        "past this point."
                    ),
                    next_action="Needs manual investigation or further mapping to continue automating subsequent pages",
                )
            finally:
                browser.close()

    return flow
