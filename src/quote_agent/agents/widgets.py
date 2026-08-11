"""Playwright interaction functions for each widget type actually observed
on real Ontario auto-insurance quote forms (ThinkInsure, Onlia).

Each function assumes the caller (a future observe-decide-act loop) has
already resolved *which* field this is and *what* value to put in it --
these functions only handle *how* to interact with a given widget type once
that decision has been made. Kept as small, composable functions rather
than one dispatcher, since widget-type detection belongs with the loop
that reads the page, not hardcoded here.
"""

import calendar
import re
from datetime import date

from playwright.sync_api import Locator, Page

_MONTH_NAMES = [calendar.month_name[i] for i in range(1, 13)]
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def fill_text(locator: Locator, value: str) -> None:
    """A plain text input."""
    locator.fill(value)


def select_native(locator: Locator, value: str) -> None:
    """A real <select> element. Matches by visible option text, not the
    underlying option value, since the mapping layer deals in human-facing
    values (e.g. "Ontario"), not implementation details (e.g. "ON").
    """
    locator.select_option(label=value)


def select_custom_dropdown(page: Page, trigger: Locator, value: str) -> None:
    """A div/button-based ARIA combobox (role="combobox" trigger,
    role="listbox"/role="option" options) -- common in modern component
    libraries even when not a native <select>. Clicks the trigger to open
    it, then clicks whichever option's visible text matches.
    """
    trigger.click()
    page.get_by_role("option", name=value, exact=False).first.click()


def click_radio_or_toggle(group: Locator, value: str) -> None:
    """A radio group or toggle-pill group (native <input type="radio">, or
    role="radio" elements styled as buttons/chips). Clicks whichever
    option's visible text matches -- works for either since both expose
    their choice as readable text.
    """
    group.get_by_text(value, exact=False).first.click()


def set_checkbox(locator: Locator, value: bool) -> None:
    """A checkbox. value=True checks it, False unchecks it -- idempotent
    either way, unlike a plain .click().
    """
    if value:
        locator.check()
    else:
        locator.uncheck()


def adjust_stepper(page: Page, value_selector: str, plus_selector: str, minus_selector: str, target: int) -> None:
    """A +/- counter with no direct text entry (e.g. ThinkInsure's
    tickets/accidents/suspensions counts). Reads the currently displayed
    value and clicks + or - repeatedly until it reaches the target.
    """
    current = int(page.locator(value_selector).inner_text().strip())
    step_count = abs(target - current)
    if step_count == 0:
        return
    step_locator = page.locator(plus_selector if target > current else minus_selector)
    for _ in range(step_count):
        step_locator.click()


def _parse_month_year(text: str) -> tuple[int, int]:
    lowered = text.lower()
    for i, name in enumerate(_MONTH_NAMES, start=1):
        if name.lower() in lowered:
            month = i
            break
    else:
        raise ValueError(f"Could not find a recognizable month name in {text!r}")

    year_match = _YEAR_PATTERN.search(text)
    if not year_match:
        raise ValueError(f"Could not find a 4-digit year in {text!r}")
    return month, int(year_match.group())


def set_date(
    page: Page,
    field: Locator,
    target: date,
    header_selector: str,
    prev_selector: str,
    next_selector: str,
    day_container_selector: str | None = None,
) -> None:
    """A calendar-popup date field -- seen on both ThinkInsure and Onlia,
    where typing directly into the field doesn't register and a calendar
    must be opened and navigated instead.

    Clicks the field to open the calendar, reads the currently displayed
    month/year from header_selector (expects a recognizable month name
    plus a 4-digit year, e.g. "August 2026"), clicks prev_selector/
    next_selector however many times are needed to reach the target
    month, then clicks the matching day number. day_container_selector
    scopes the day-number search (recommended, to avoid matching an
    unrelated number elsewhere on the page); omit it to search the whole
    page.
    """
    field.click()

    header_text = page.locator(header_selector).inner_text()
    current_month, current_year = _parse_month_year(header_text)
    delta = (target.year - current_year) * 12 + (target.month - current_month)

    step_locator = page.locator(next_selector if delta > 0 else prev_selector)
    for _ in range(abs(delta)):
        step_locator.click()

    day_scope = page.locator(day_container_selector) if day_container_selector else page
    day_scope.get_by_text(str(target.day), exact=True).first.click()


def resolve_autocomplete(
    page: Page,
    field: Locator,
    query: str,
    suggestion_selector: str,
    match_text: str | None = None,
) -> None:
    """A type-ahead autocomplete (e.g. Onlia's address field, backed by
    Canada Post's AddressComplete widget) -- typing alone doesn't set a
    valid value, a suggestion must be clicked. Presses each character of
    query as a real keystroke, waits for at least one suggestion to
    appear, then clicks the one matching match_text (substring,
    case-sensitive as typed) or just the first suggestion if match_text
    is None.

    Deliberately uses press_sequentially rather than fill: confirmed
    against the real live Onlia page that AddressComplete's suggestion
    search is wired to actual keystroke events and never fires on a
    single bulk value-set, even though the field ends up holding the
    right-looking text either way -- fill() alone leaves the field
    "typed but never selected," which is exactly the stuck state this
    function exists to avoid.
    """
    field.click()  # confirmed necessary against the real widget: press_sequentially alone
    # (without a real prior click/focus) never triggered the suggestion search on Onlia's page
    field.press_sequentially(query, delay=80)
    suggestions = page.locator(suggestion_selector)
    suggestions.first.wait_for(state="visible")
    # Each keystroke fires its own debounced search request (confirmed against the
    # real widget: typing "1 Yonge St" alone fired ~10 separate lookups, one per
    # character), and they can resolve out of order. The list can still be
    # mid-repopulation from an earlier response right as the *last* one appears --
    # clicking immediately risked landing before the final, authoritative list
    # settled. A short pause lets in-flight responses finish arriving first.
    page.wait_for_timeout(400)
    if match_text:
        suggestions.get_by_text(match_text, exact=False).first.click()
    else:
        suggestions.first.click()
    # The widget processes a selection asynchronously (confirmed against the real
    # widget: reading the field's value/validity state immediately after the click
    # still showed the raw typed text, not the selected suggestion -- it needed a
    # moment to finish before the field actually reflected the selection).
    page.wait_for_timeout(1000)


def select_multiple_cards(container: Locator, values: list[str]) -> None:
    """A set of independently-toggled cards, not mutually exclusive like a
    radio group -- e.g. Onlia's "select all additional drivers that
    should be in the policy" step. Clicks each card whose visible text
    matches one of `values`. Cards not named in `values` are left as
    whatever their current state already is -- pass the complete set of
    names that should end up selected, since this doesn't deselect
    anything on its own.
    """
    for value in values:
        container.get_by_text(value, exact=False).first.click()
