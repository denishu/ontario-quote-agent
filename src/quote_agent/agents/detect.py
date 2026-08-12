"""Best-effort widget-type detection from a single form-control element's
tag and ARIA attributes.

Deliberately conservative: only classifies the cases that are reliably
inferable from one element in isolation (native select, checkbox, ARIA
combobox, plain text, a single radio option). Steppers and date pickers
are structurally ambiguous from one element alone -- a stepper's +/-
buttons carry no distinguishing role, and a plain-looking readonly text
input might be a date picker that silently ignores direct typing, which
we confirmed firsthand on real sites. Those return UNKNOWN rather than a
wrong guess -- the caller is expected to supply an explicit type hint for
those cases instead.

NOTE: autocomplete="off" was tried as a signal for "this is a custom
JS-driven suggestion widget" but confirmed against a real site (Onlia) to
be unreliable -- ordinary text fields there use it too, just to disable
the browser's own native autofill, with no relation to whether a custom
dropdown exists behind the field. Removed rather than left in producing
false positives on plain fillable fields.
"""

from enum import Enum

from playwright.sync_api import Locator

_TEXT_LIKE_INPUT_TYPES = {None, "text", "email", "tel"}


class WidgetType(str, Enum):
    TEXT = "text"
    NATIVE_SELECT = "native_select"
    CUSTOM_DROPDOWN = "custom_dropdown"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    UNKNOWN = "unknown"


def detect_widget_type(locator: Locator) -> WidgetType:
    tag = locator.evaluate("el => el.tagName.toLowerCase()")
    if tag == "select":
        return WidgetType.NATIVE_SELECT

    input_type = locator.get_attribute("type")
    if input_type == "checkbox":
        return WidgetType.CHECKBOX
    if input_type == "radio":
        return WidgetType.RADIO

    role = locator.get_attribute("role")
    if role == "combobox":
        return WidgetType.CUSTOM_DROPDOWN
    if role in ("radio", "radiogroup"):
        return WidgetType.RADIO
    if locator.locator('[role="radio"]').count() > 0:
        # The element itself carries no role, but wraps one or more
        # role="radio" descendants -- confirmed on a real site (Aviva),
        # where a fragmented multi-option question's real control ends up
        # being the plain <div> shared parent of several single-radio
        # radiogroups, not something with role="radiogroup" of its own.
        return WidgetType.RADIO

    if tag in ("input", "textarea") and input_type in _TEXT_LIKE_INPUT_TYPES:
        if locator.get_attribute("readonly") is not None:
            return WidgetType.UNKNOWN  # likely a date picker -- typing doesn't register
        return WidgetType.TEXT

    return WidgetType.UNKNOWN
