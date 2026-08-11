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


def test_readonly_date_field_is_unknown_not_text(page):
    # Confirmed firsthand: typing into these silently fails on real sites.
    # Must not be classified as a plain fillable text field.
    assert detect_widget_type(page.locator("#start-date")) == WidgetType.UNKNOWN


def test_autocomplete_off_field_is_unknown_not_text(page):
    assert detect_widget_type(page.locator("#address")) == WidgetType.UNKNOWN


def test_stepper_button_is_unknown(page):
    # A stepper's +/- buttons carry no distinguishing role on their own --
    # this is a known, accepted limitation of single-element detection.
    assert detect_widget_type(page.locator("#tickets-plus")) == WidgetType.UNKNOWN
