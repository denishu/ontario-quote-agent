"""Aviva's full intake flow (myaviva.avivainsurance.ca/avivaquoter/bol/
auto/...) -- Car Details -> Car Use -> Driver Details, all mapped and
validated against the real live site. Fills every field across all three
pages automatically (vehicle YMM/purchase date/condition/anti-theft/
winter tires, annual km, commute days/distance, coverage start date,
driver name/DOB/sex/marital status, continuous-insurance duration) using
the fully generic fill loop (fill_visible_fields + run_flow_steps) plus
one Aviva-specific step: dismissing a modal that never closes on its own.

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

Confirmed live (2026-08-12): after Driver Details, the flow reaches its
actual quote-generation trigger and presents exactly two options --
"Email me my quote" or "Buy now". There is no on-page premium/coverage
display, PDF, or other scrapable quote artifact at all. Both remaining
options are out of scope by design: "Buy now" is a purchase/binding
action automation must never click, and "Email me my quote" would
require reading the applicant's real inbox (no email-scraping
capability, out of scope). Always ends in MANUAL_HANDOFF here -- not a
safety boundary the way Onlia's consent checkpoint is, but a genuine
dead end in what this site's own flow can offer to an automated client.

Also confirmed live: Aviva's Driver Details page carries two invisible
anti-bot honeypot fields (hp-label class, aria-hidden labels pointing at
tabindex=-1 inputs) -- both correctly detected and left unfilled by
discover_fields' visible-label check.

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
                        "Full intake flow (Car Details, Car Use, Driver Details) completed and "
                        "reached the quote-generation trigger, which offers only \"Email me my "
                        "quote\" or \"Buy now\" -- no on-page premium/coverage display, PDF, or "
                        "other scrapable quote artifact exists."
                    ),
                    next_action=(
                        "Requires a human to either complete the purchase (out of scope -- this "
                        "tool never binds a policy) or retrieve the emailed quote manually "
                        "(out of scope -- no email-scraping capability)"
                    ),
                )
            finally:
                browser.close()

    return flow
