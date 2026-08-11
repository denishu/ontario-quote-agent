"""The observe-decide-act loop: reads whatever fields are currently on a
page, resolves each one against the intake schema, and fills in whatever
it can confidently handle -- text, native selects, checkboxes, radio/
toggle groups, and ARIA comboboxes.

Doesn't click any button -- the caller decides that, since knowing which
button is "Continue" versus a sensitive action needs page-specific
judgment, not something this function should guess at. Doesn't attempt
fields whose widget type can't be determined from a single element
(steppers, date pickers, autocomplete): those get reported, not silently
skipped, so the caller knows they need explicit handling.
"""

from dataclasses import dataclass, field
from typing import Callable

from playwright.sync_api import Locator, Page

from quote_agent.agents.detect import WidgetType, detect_widget_type
from quote_agent.agents.policy import CaptchaDetected, detect_captcha
from quote_agent.agents.widgets import (
    click_radio_or_toggle,
    fill_text,
    select_custom_dropdown,
    select_native,
    set_checkbox,
)
from quote_agent.mapping import get_field_value, resolve_field
from quote_agent.models import IntakeProfile


@dataclass
class FillReport:
    filled: dict[str, str] = field(default_factory=dict)  # label -> resolved field path
    unresolved: list[str] = field(default_factory=list)  # labels with no schema match
    skipped_unknown_widget: list[str] = field(default_factory=list)  # labels whose widget type is ambiguous


def discover_fields(page: Page) -> list[tuple[str, Locator]]:
    """Find (label text, control locator) pairs for whatever's currently
    on the page: both <label for="..."> associations and wrapping
    <label><input>...</label> patterns (both are common in the wild), plus
    role="radiogroup" elements (using their aria-label) for radio/toggle
    groups. A starting point validated against the local fixture -- real
    sites will likely need this refined as their specific patterns are
    discovered.
    """
    pairs: list[tuple[str, Locator]] = []

    for label in page.locator("label").all():
        control_id = label.get_attribute("for")
        control = page.locator(f"#{control_id}") if control_id else label.locator("input, select, textarea")
        if control.count() == 0:
            continue
        text = label.inner_text().strip()
        if text:
            pairs.append((text, control.first))

    for group in page.locator('[role="radiogroup"]').all():
        text = (group.get_attribute("aria-label") or "").strip()
        if text:
            pairs.append((text, group))

    return pairs


def fill_visible_fields(
    page: Page,
    intake: IntakeProfile,
    *,
    vehicle_index: int = 0,
    household_index: int = 0,
    llm_fallback: Callable[[str], str | None] | None = None,
) -> FillReport:
    """Observe the current page and fill in whatever it can confidently
    resolve and interact with. Raises CaptchaDetected immediately if the
    page shows a bot-wall indicator -- never attempts to work around it,
    and never fills anything if one is present.
    """
    if detect_captcha(page.content()):
        raise CaptchaDetected(raw_evidence_text=page.content())

    report = FillReport()

    for label_text, control in discover_fields(page):
        path = resolve_field(label_text, llm_fallback=llm_fallback)
        if path is None:
            report.unresolved.append(label_text)
            continue

        widget_type = detect_widget_type(control)
        if widget_type is WidgetType.UNKNOWN:
            report.skipped_unknown_widget.append(label_text)
            continue

        value = get_field_value(intake, path, vehicle_index=vehicle_index, household_index=household_index)
        _apply(page, control, widget_type, value)
        report.filled[label_text] = path

    return report


def _apply(page: Page, control: Locator, widget_type: WidgetType, value: object) -> None:
    if widget_type is WidgetType.TEXT:
        fill_text(control, str(value))
    elif widget_type is WidgetType.NATIVE_SELECT:
        select_native(control, str(value))
    elif widget_type is WidgetType.CUSTOM_DROPDOWN:
        select_custom_dropdown(page, control, str(value))
    elif widget_type is WidgetType.CHECKBOX:
        set_checkbox(control, bool(value))
    elif widget_type is WidgetType.RADIO:
        click_radio_or_toggle(control, str(value))
