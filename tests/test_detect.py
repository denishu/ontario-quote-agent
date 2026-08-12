from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from quote_agent.agents.detect import WidgetType, detect_widget_type

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "widgets.html").resolve().as_uri()


@pytest.fixture
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE_URL)
        yield page
        browser.close()


def test_detects_plain_text_input(page):
    assert detect_widget_type(page.locator("#first-name")) == WidgetType.TEXT


def test_detects_native_select(page):
    assert detect_widget_type(page.locator("#province")) == WidgetType.NATIVE_SELECT


def test_detects_custom_dropdown_by_combobox_role(page):
    assert detect_widget_type(page.locator("#licence-status-trigger")) == WidgetType.CUSTOM_DROPDOWN


def test_detects_radio_group_by_radiogroup_role(page):
    assert detect_widget_type(page.locator("#vehicle-use-group")) == WidgetType.RADIO


def test_detects_checkbox(page):
    assert detect_widget_type(page.locator("#winter-tires")) == WidgetType.CHECKBOX


def test_detects_radio_by_role(page):
    option = page.locator("#vehicle-use-group [role='radio']").first
    assert detect_widget_type(option) == WidgetType.RADIO


def test_detects_radio_via_role_less_wrapper_of_radio_descendants(page):
    # "#fragmented-condition" carries no role of its own -- confirmed on a
    # real site (Aviva) that a fragmented multi-option question's real
    # shared-parent control ends up being a plain <div> like this, not
    # something with role="radiogroup" itself.
    assert detect_widget_type(page.locator("#fragmented-condition")) == WidgetType.RADIO


def test_readonly_date_field_is_unknown_not_text(page):
    # Confirmed firsthand: typing into these silently fails on real sites.
    # Must not be classified as a plain fillable text field.
    assert detect_widget_type(page.locator("#start-date")) == WidgetType.UNKNOWN


def test_native_date_input_is_treated_as_text(page):
    # Unlike the readonly case above (a custom JS date picker where typing
    # silently does nothing), a real type="date" input has no such
    # ambiguity -- confirmed on a real site (Aviva) that Playwright's
    # fill() works directly against one given an ISO "YYYY-MM-DD" string.
    assert detect_widget_type(page.locator("#coverage-start")) == WidgetType.TEXT


def test_autocomplete_off_field_is_treated_as_text(page):
    # Confirmed against a real saved page (Onlia): autocomplete="off" is
    # not a reliable signal for "this is a custom JS-driven suggestion
    # widget" -- plain First/Last Name and Licence Number fields there use
    # it too, purely to disable the browser's own native autofill. A
    # single element gives no reliable way to tell those apart from a
    # genuine type-ahead widget like this fixture's address field, so this
    # is now treated as plain text -- a known, accepted trade-off (see
    # test_loop.py for the address-specific consequence).
    assert detect_widget_type(page.locator("#address")) == WidgetType.TEXT


def test_stepper_button_is_unknown(page):
    # A stepper's +/- buttons carry no distinguishing role on their own --
    # this is a known, accepted limitation of single-element detection.
    assert detect_widget_type(page.locator("#tickets-plus")) == WidgetType.UNKNOWN
