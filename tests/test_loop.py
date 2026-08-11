from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from quote_agent.agents import CaptchaDetected, fill_visible_fields
from quote_agent.models import (
    Address,
    Consent,
    ConsentMode,
    CoverageConfig,
    Identity,
    InsuranceHistory,
    IntakeProfile,
    Vehicle,
)

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "widgets.html").resolve().as_uri()


def make_intake() -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(legal_name="Jane Applicant", date_of_birth="1990-01-01"),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        # NOTE: province stored here as the display label ("Ontario") to match this fixture's
        # <select> options -- a real intake.json more likely stores the code ("ON"). Storing
        # a value that matches the schema but not necessarily the site's own option text is a
        # real, expected friction point once this runs against a genuine live site.
        address=Address(street="123 Main St", city="Toronto", province="Ontario", postal_code="M5V 3A8"),
        vehicles=[
            Vehicle(
                vin="VIN0",
                model_year=2020,
                make="Toyota",
                model="Corolla",
                ownership="owned",
                primary_use="commute",
                annual_km=12000,
                winter_tires=True,
            )
        ],
        insurance_history=InsuranceHistory(),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01", third_party_liability_limit=2_000_000, dcpd_included=True
        ),
    )


@pytest.fixture
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE_URL)
        yield page
        browser.close()


def test_fill_visible_fields_fills_known_aliased_fields_without_llm(page):
    intake = make_intake()

    def failing_llm(label: str) -> str | None:
        raise AssertionError(f"llm_fallback should not be needed for {label!r}")

    report = fill_visible_fields(page, intake, llm_fallback=failing_llm)

    assert page.locator("#first-name").input_value() == "Jane"
    assert page.locator("#province").input_value() == "ON"
    assert page.locator("#winter-tires").is_checked()
    # stored value is "commute", displayed option is "Commuting" -- not a
    # substring match, only works via resolve_display_value's alias table
    assert page.locator('#vehicle-use-group [role="radio"][aria-checked="true"]').inner_text() == "Commuting"

    assert report.filled["First Name"] == "identity.first_name"
    assert report.filled["Province"] == "address.province"
    assert report.filled["Do you have winter tires?"] == "vehicles[].winter_tires"
    assert report.filled["Vehicle use"] == "vehicles[].primary_use"


def test_fill_visible_fields_reports_resolved_but_unfillable_widgets(page):
    # "Start Date" and "Street Address" both resolve via known aliases, but
    # their widgets (readonly date field, autocomplete=off address) can't
    # be classified from a single element -- they must be reported, not
    # silently skipped or incorrectly filled as plain text.
    intake = make_intake()
    report = fill_visible_fields(page, intake)

    assert "Start Date" in report.skipped_unknown_widget
    assert "Street Address" in report.skipped_unknown_widget
    assert page.locator("#start-date").input_value() == ""
    assert page.locator("#address").input_value() == ""


def test_fill_visible_fields_reports_genuinely_unresolved_labels(page):
    page.evaluate(
        """() => {
            const label = document.createElement('label');
            label.setAttribute('for', 'mystery-field');
            label.textContent = 'Completely novel unmapped question';
            const input = document.createElement('input');
            input.type = 'text';
            input.id = 'mystery-field';
            document.body.appendChild(label);
            document.body.appendChild(input);
        }"""
    )
    intake = make_intake()
    report = fill_visible_fields(page, intake, llm_fallback=None)

    assert "Completely novel unmapped question" in report.unresolved
    assert page.locator("#mystery-field").input_value() == ""


def test_fill_visible_fields_ignores_invisible_recaptcha_infrastructure(page):
    # Confirmed against a real saved page: passive/invisible reCAPTCHA
    # (a script tag, a corner badge, a hidden response field -- present
    # on nearly every modern site, whether or not any challenge is ever
    # shown) makes "recaptcha" appear in the raw HTML source without any
    # visible text a human would actually see. Must not false-positive.
    page.evaluate(
        """() => {
            document.body.innerHTML += `
                <script src="https://www.google.com/recaptcha/api.js" async></script>
                <div class="grecaptcha-badge" style="visibility: hidden;"></div>
                <textarea id="g-recaptcha-response" class="g-recaptcha-response" style="display:none;"></textarea>
            `;
        }"""
    )
    intake = make_intake()

    report = fill_visible_fields(page, intake)  # must not raise CaptchaDetected

    assert page.locator("#first-name").input_value() == "Jane"


def test_fill_visible_fields_raises_on_captcha_without_filling_anything(page):
    page.evaluate(
        "() => { document.body.innerHTML += '<div>Please complete the CAPTCHA below</div>'; }"
    )
    intake = make_intake()

    with pytest.raises(CaptchaDetected):
        fill_visible_fields(page, intake)

    assert page.locator("#first-name").input_value() == ""
