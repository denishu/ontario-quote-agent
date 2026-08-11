from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from quote_agent.mapping.value_aliases import resolve_display_value

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "widgets.html").resolve().as_uri()


@pytest.fixture
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FIXTURE_URL)
        yield page
        browser.close()


def test_resolve_display_value_finds_the_aliased_variant(page):
    group = page.locator("#vehicle-use-group")
    # "commute" itself doesn't appear anywhere in the group (only "Commuting" does)
    assert group.get_by_text("commute", exact=False).count() == 0
    assert resolve_display_value(group, "commute") == "commuting"


def test_resolve_display_value_prefers_direct_match_when_present(page):
    group = page.locator("#vehicle-use-group")
    assert resolve_display_value(group, "business") == "business"


def test_resolve_display_value_falls_back_to_original_value_when_nothing_matches(page):
    group = page.locator("#vehicle-use-group")
    assert resolve_display_value(group, "totally-unrelated-value") == "totally-unrelated-value"
