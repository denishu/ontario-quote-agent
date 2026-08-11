"""Onlia's personal-info step (app.onlia.ca/#/auto/personal-info) -- the
only part of Onlia's flow mapped and validated against the real live site
so far. Fills name, address, policy-start-date, and licence number
automatically, then always ends in a MANUAL_HANDOFF: Onlia gates its
Continue/"Start My Quote" button behind a required Terms of Use/Privacy
Policy consent checkbox (confirmed live -- clicking it triggers Onlia
ordering driving-record reports), which this flow will never check on its
own, per the hard rule against auto-consenting. That means this flow can
never return QuoteObtained by itself -- its job ends at a clean,
evidence-backed hand-off once everything safe to fill has been filled.
Everything past this page (vehicle details, driving history, etc.) is
unmapped -- this flow was never exercised past the personal-info step.

Deliberately not covered by the pytest suite: this launches a real
browser against a real live third-party site every time it runs, which
isn't something to run repeatedly/automatically in CI. Validated instead
by direct, repeated runs against the live page during development (see
commit history) -- the underlying primitives it calls (resolve_autocomplete,
set_date, fill_visible_fields, discover_fields) all have full local
fixture coverage of their own.

headless defaults to True, but confirmed live that Onlia's invisible
reCAPTCHA v3 risk-scores headless Chromium's fingerprint low enough to
actually fail the check -- the page shows a real, human-visible "Captcha
validation failed" message, which fill_visible_fields correctly detects
and raises CaptchaDetected for (this is the system working as intended,
not a bug: never bypass a CAPTCHA, never retry around it). Headed mode
did not trigger this in the same testing. Rather than silently defaulting
to headless=False (which would just be choosing the mode that happens not
to get blocked, uncomfortably close to evasion) this stays an explicit
opt-in the caller has to choose, on their own real desktop session, with
that trade-off in view.
"""

from datetime import date as _date

from playwright.sync_api import sync_playwright

from quote_agent.agents.flow import find_next_action
from quote_agent.agents.loop import discover_fields, fill_visible_fields
from quote_agent.agents.policy import guard_against_sensitive_action
from quote_agent.agents.web import NonQuoteOutcome, QuoteObtained
from quote_agent.agents.widgets import resolve_autocomplete, set_date
from quote_agent.models import IntakeProfile
from quote_agent.models.status import QuoteStatus

FORM_URL = "https://app.onlia.ca/#/auto/personal-info?Affinity_Group=Onlia&utm_content=auto_quote_button"
_MAX_STEPS = 8

# Confirmed against the live page: real address suggestions and calendar
# day cells, respectively -- see resolve_autocomplete/set_date call sites
# below for what each selector needed to exclude and why.
_ADDRESS_SUGGESTION_SELECTOR = ".pcaitem:visible"
_DATE_HEADER_SELECTOR = ".date-switch:visible"
_DATE_PREV_SELECTOR = "th.prev:visible i"
_DATE_NEXT_SELECTOR = "th.next:visible i"
_DATE_DAY_SELECTOR = ".datepicker-days:visible td.day:not(.old):not(.new):not(.disabled)"


def onlia_personal_info_flow(intake: IntakeProfile, *, headless: bool = True) -> QuoteObtained | NonQuoteOutcome:
    """Run Onlia's personal-info step end to end. Matches the WebFlow
    signature (Callable[[IntakeProfile], QuoteObtained | NonQuoteOutcome]);
    owns its own browser for the whole attempt, per that contract. The
    optional headless kwarg doesn't affect that -- run_web_attempt calls
    flow(intake) with no extra arguments, so the safe default (True)
    always applies unless a caller explicitly opts into headed mode.

    CaptchaDetected (from fill_visible_fields) and StopBeforeSensitiveAction
    (from guard_against_sensitive_action) both propagate to the caller
    rather than being caught here -- run_web_attempt is what turns those
    into the right terminal status.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            page.goto(FORM_URL, timeout=60000)
            page.wait_for_selector("#first_name", timeout=30000)

            address_handled = False
            date_handled = False

            for _ in range(_MAX_STEPS):
                labels = dict(discover_fields(page))

                # The address field is a real type-ahead widget (Canada Post's
                # AddressComplete) -- typing alone leaves it "typed but not
                # selected," a suggestion card has to actually be clicked.
                # Its label ("My address is") IS discoverable, so it's
                # intercepted here rather than going through the generic
                # fill_visible_fields path, which would just type the raw
                # value in and leave the field stuck invalid.
                if "My address is" in labels and not address_handled:
                    query = f"{intake.address.street}, {intake.address.city}"
                    resolve_autocomplete(
                        page,
                        labels["My address is"],
                        query,
                        suggestion_selector=_ADDRESS_SUGGESTION_SELECTOR,
                        match_text=intake.address.postal_code,
                    )
                    address_handled = True
                    page.keyboard.press("Enter")  # same Typeform-style advance as the name fields
                    page.wait_for_timeout(1000)
                    continue

                # The policy-start-date field ("I'd like to insure my vehicle,
                # starting on") is a real ngx-bootstrap calendar popup. Its
                # label isn't linked via for= or wrapping, so discover_fields
                # can't find it (same class of gap as a decorative label with
                # no evidence it was ever meant to point at a control) --
                # targeted directly by id instead.
                date_field = page.locator("#date_start")
                if date_field.count() > 0 and date_field.is_visible() and not date_handled:
                    target = _date.fromisoformat(intake.coverage_benchmark.effective_date)
                    set_date(
                        page,
                        date_field,
                        target,
                        header_selector=_DATE_HEADER_SELECTOR,
                        prev_selector=_DATE_PREV_SELECTOR,
                        next_selector=_DATE_NEXT_SELECTOR,
                        day_container_selector=_DATE_DAY_SELECTOR,
                    )
                    date_handled = True
                    continue

                report = fill_visible_fields(page, intake)

                next_action = find_next_action(page)
                if next_action is not None:
                    label = next_action.inner_text().strip() or "Continue"
                    guard_against_sensitive_action(label, raw_evidence_text=page.inner_text("body"))
                    next_action.click()
                    page.wait_for_timeout(1000)
                    continue

                if report.filled:
                    # Onlia's personal-info step is a Typeform-style
                    # conversational form: its Continue button exists in the
                    # DOM the whole time but stays hidden until Enter is
                    # pressed in the field -- confirmed live, there's no
                    # visible button for find_next_action to ever find here.
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1000)
                    continue

                # Nothing left to fill and no visible way to advance. Expected,
                # not a failure: Onlia's Continue/"Start My Quote" button stays
                # hidden until the Terms of Use/Privacy Policy checkbox is
                # checked, which this flow never does on its own.
                return NonQuoteOutcome(
                    status=QuoteStatus.MANUAL_HANDOFF,
                    raw_evidence_text=page.inner_text("body"),
                    failure_reason=(
                        "Reached Onlia's consent checkpoint (Terms of Use / Privacy Policy) -- "
                        "everything fillable up to this point was completed automatically."
                    ),
                    next_action="Applicant must check the Terms of Use/Privacy Policy box and click Continue manually",
                )

            return NonQuoteOutcome(
                status=QuoteStatus.MANUAL_HANDOFF,
                raw_evidence_text=page.inner_text("body"),
                failure_reason=f"Personal-info step did not resolve within {_MAX_STEPS} steps",
                next_action="Needs manual investigation -- possible unmapped field or changed page structure",
            )
        finally:
            browser.close()
