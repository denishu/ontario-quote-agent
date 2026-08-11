"""Best-effort widget-type detection from a single form-control element's
tag and ARIA attributes.

Deliberately conservative: only classifies the cases that are reliably
inferable from one element in isolation (native select, checkbox, ARIA
combobox, plain text, a single radio option). Steppers, date pickers, and
autocomplete fields are structurally ambiguous from one element alone --
a stepper's +/- buttons carry no distinguishing role, and a plain-looking
text input might be a date picker (readonly) or a custom autocomplete
(autocomplete="off") that silently ignores direct typing, which we
confirmed firsthand on real sites. Those return UNKNOWN rather than a
wrong guess -- the caller is expected to supply an explicit type hint for
those cases instead.
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

    if tag in ("input", "textarea") and input_type in _TEXT_LIKE_INPUT_TYPES:
        if locator.get_attribute("readonly") is not None:
            return WidgetType.UNKNOWN  # likely a date picker -- typing doesn't register
        if locator.get_attribute("autocomplete") == "off":
            return WidgetType.UNKNOWN  # likely a custom JS-driven autocomplete
        return WidgetType.TEXT

    return WidgetType.UNKNOWN
