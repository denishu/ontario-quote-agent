"""Playwright interaction functions for each widget type actually observed
on real Ontario auto-insurance quote forms (ThinkInsure, Onlia).

Each function assumes the caller (a future observe-decide-act loop) has
already resolved *which* field this is and *what* value to put in it --
these functions only handle *how* to interact with a given widget type once
that decision has been made. Kept as small, composable functions rather
than one dispatcher, since widget-type detection belongs with the loop
that reads the page, not hardcoded here.
"""

from playwright.sync_api import Locator, Page


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
