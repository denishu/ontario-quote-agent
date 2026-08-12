from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from quote_agent.agents import StopBeforeSensitiveAction, find_next_action, run_flow_steps
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

MULTISTEP_URL = (Path(__file__).parent / "fixtures" / "multistep.html").resolve().as_uri()
REVEAL_ON_FILL_URL = (Path(__file__).parent / "fixtures" / "reveal_on_fill.html").resolve().as_uri()


def make_intake() -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(legal_name="Jane Applicant", date_of_birth="1990-01-01"),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        address=Address(street="123 Main St", city="Toronto", postal_code="M5V 3A8"),
        vehicles=[
            Vehicle(
                vin="VIN0",
                model_year=2020,
                make="Toyota",
                model="Corolla",
                ownership="owned",
                primary_use="commute",
                annual_km=12000,
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
        yield page
        browser.close()


def test_find_next_action_finds_only_the_visible_submit_button(page):
    page.goto(MULTISTEP_URL)
    action = find_next_action(page)
    assert action is not None
    assert action.get_attribute("id") == "next-1"  # step-2's button exists in DOM but is hidden


def test_run_flow_steps_completes_a_multi_step_flow(page):
    page.goto(MULTISTEP_URL)
    intake = make_intake()

    result = run_flow_steps(page, intake, llm_fallback=None)

    assert page.locator("#q1").input_value() == "Jane"
    assert page.locator("#q2").input_value() == "M5V 3A8"
    assert page.locator("#step-3").is_visible()

    # step 1 (filled + advanced), step 2 (filled + advanced), step 3 (filled -- nothing to
    # fill -- no next action found, loop stops)
    assert len(result.steps) == 3
    assert result.steps[0].advanced and result.steps[0].changed
    assert result.steps[1].advanced and result.steps[1].changed
    assert not result.steps[2].advanced


def test_run_flow_steps_fills_a_field_revealed_by_an_earlier_fill_within_the_same_step(page):
    # "One-way commute km" doesn't exist meaningfully in the DOM until
    # "Commute days" is answered -- confirmed on a real site (Aviva).
    # Without re-observing the page mid-step, this field is never
    # discovered, the site's own Continue button then refuses to
    # navigate while it's still empty, and the loop stops for good
    # believing nothing more can be done.
    page.goto(REVEAL_ON_FILL_URL)
    intake = make_intake()
    intake.vehicles[0].commute_days_per_week = 5
    intake.vehicles[0].commute_one_way_km = 8.5

    def llm_fallback(label: str) -> str | None:
        if "commute days" in label.lower():
            return "vehicles[].commute_days_per_week"
        if "one-way commute km" in label.lower():
            return "vehicles[].commute_one_way_km"
        return None

    run_flow_steps(page, intake, llm_fallback=llm_fallback)

    assert page.locator("#one-way-km").input_value() == "8.5"
    assert page.locator("#step-2").is_visible()


def test_run_flow_steps_stops_before_a_sensitive_action(page):
    page.goto(MULTISTEP_URL)
    page.evaluate(
        """() => {
            document.getElementById('next-1').textContent = 'Submit Application';
        }"""
    )
    intake = make_intake()

    with pytest.raises(StopBeforeSensitiveAction):
        run_flow_steps(page, intake, llm_fallback=None)

    # first-name field still got filled (that part is safe), but nothing was clicked
    assert page.locator("#q1").input_value() == "Jane"
    assert page.locator("#step-1").is_visible()
    assert not page.locator("#step-2").is_visible()
