from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from quote_agent.agents.widgets import (
    adjust_stepper,
    click_radio_or_toggle,
    fill_text,
    select_custom_dropdown,
    select_native,
    set_checkbox,
    set_date,
)

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "widgets.html").resolve().as_uri()


@pytest.fixture
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE_URL)
        yield page
        browser.close()


def test_fill_text(page):
    fill_text(page.locator("#first-name"), "Jane")
    assert page.locator("#first-name").input_value() == "Jane"


def test_select_native_matches_by_visible_label(page):
    select_native(page.locator("#province"), "Ontario")
    assert page.locator("#province").input_value() == "ON"


def test_select_custom_dropdown(page):
    select_custom_dropdown(page, page.locator("#licence-status-trigger"), "Suspended")
    assert page.locator("#licence-status-trigger").inner_text() == "Suspended"


def test_click_radio_or_toggle_selects_matching_option(page):
    group = page.locator("#vehicle-use-group")
    click_radio_or_toggle(group, "Business")
    assert group.locator('[role="radio"][aria-checked="true"]').inner_text() == "Business"


def test_set_checkbox_checks_and_unchecks(page):
    checkbox = page.locator("#winter-tires")
    set_checkbox(checkbox, True)
    assert checkbox.is_checked()
    set_checkbox(checkbox, False)
    assert not checkbox.is_checked()


def test_adjust_stepper_increments_to_target(page):
    adjust_stepper(page, "#tickets-value", "#tickets-plus", "#tickets-minus", target=3)
    assert page.locator("#tickets-value").inner_text() == "3"


def test_adjust_stepper_decrements_to_target(page):
    adjust_stepper(page, "#tickets-value", "#tickets-plus", "#tickets-minus", target=5)
    adjust_stepper(page, "#tickets-value", "#tickets-plus", "#tickets-minus", target=2)
    assert page.locator("#tickets-value").inner_text() == "2"


def test_adjust_stepper_no_op_when_already_at_target(page):
    adjust_stepper(page, "#tickets-value", "#tickets-plus", "#tickets-minus", target=0)
    assert page.locator("#tickets-value").inner_text() == "0"


def _set_date(page, target: date) -> None:
    set_date(
        page,
        page.locator("#start-date"),
        target,
        header_selector="#cal-header",
        prev_selector="#cal-prev",
        next_selector="#cal-next",
        day_container_selector="#cal-days",
    )


def test_set_date_within_the_currently_displayed_month(page):
    _set_date(page, date(2026, 8, 20))
    assert page.locator("#start-date").input_value() == "20-08-2026"


def test_set_date_navigates_forward_to_a_later_month(page):
    _set_date(page, date(2026, 10, 5))
    assert page.locator("#start-date").input_value() == "05-10-2026"


def test_set_date_navigates_backward_after_moving_forward(page):
    _set_date(page, date(2026, 10, 5))  # move forward first
    _set_date(page, date(2026, 8, 15))  # then back
    assert page.locator("#start-date").input_value() == "15-08-2026"
