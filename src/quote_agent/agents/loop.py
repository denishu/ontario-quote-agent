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
from quote_agent.mapping.value_aliases import resolve_display_value
from quote_agent.models import IntakeProfile


@dataclass
class FillReport:
    filled: dict[str, str] = field(default_factory=dict)  # label -> resolved field path
    unresolved: list[str] = field(default_factory=list)  # labels with no schema match
    skipped_unknown_widget: list[str] = field(default_factory=list)  # labels whose widget type is ambiguous
    failed_to_fill: dict[str, str] = field(default_factory=dict)  # label -> error, resolved+classified but interaction still failed
    no_data: dict[str, str] = field(default_factory=dict)  # label -> resolved field path, but intake has no value for it


def _resolve_labeled_control(label: Locator) -> Locator | None:
    """Resolve the control a <label> actually refers to. Tries `for="..."`
    first, then the wrapping <label><input>...</label> pattern.

    If `for="..."` is present but doesn't resolve to anything visible,
    falls back to the nearest visible, non-hidden form control in the
    label's own parent element. That fallback is scoped to only this
    case -- a `for=` that was set but is broken -- rather than to any
    label without a resolvable control, because those are different
    situations: confirmed on a real site (Onlia) where a label's
    `for="postal_code"` pointed at a hidden decoy input that doesn't even
    carry that id (likely stale after a refactor), silently orphaning the
    label from the real, visible text field sitting right next to it in
    the same row -- a broken reference that clearly meant to point at
    *something*. A label with no `for=` and no wrapped control at all
    (e.g. plain legal-disclaimer text sitting near an unrelated checkbox)
    isn't that -- guessing a nearby control for it risks pairing
    decorative text with a control it was never meant to label, so that
    case is left unresolved rather than guessed at.
    """
    control_id = label.get_attribute("for")
    if control_id:
        by_id = label.page.locator(f"#{control_id}")
        if by_id.count() > 0 and by_id.first.is_visible():
            return by_id.first

        nearby = label.locator("xpath=..").locator("input:not([type=hidden]), select, textarea")
        for i in range(nearby.count()):
            candidate = nearby.nth(i)
            if candidate.is_visible():
                return candidate
        return None

    wrapped = label.locator("input, select, textarea")
    visible_wrapped = [wrapped.nth(i) for i in range(wrapped.count()) if wrapped.nth(i).is_visible()]
    if len(visible_wrapped) == 1:
        return visible_wrapped[0]
    # A label wrapping *more than one* control (no for=) is ambiguous, not
    # just permissive -- confirmed on a real site (Aviva): a group-level
    # <label>Date of birth</label> wraps all three separate day/month/year
    # boxes with no for= of its own. Blindly picking the first one doesn't
    # just mislabel it -- it marks that control as already-discovered,
    # which then blocks its own correct, distinct aria-label
    # ("Enter the month you were born") from ever being tried at all,
    # silently swapping in the whole unsplit date_of_birth value instead.
    return None


_DISCOVERED_MARKER = "data-qa-agent-discovered"


def discover_fields(page: Page) -> list[tuple[str, Locator]]:
    """Find (label text, control locator) pairs for whatever's currently
    on the page: both <label for="..."> associations and wrapping
    <label><input>...</label> patterns (both are common in the wild),
    role="radiogroup" elements (using their aria-label) for radio/toggle
    groups, and a control's own aria-label when it has no separate <label>
    at all. A starting point validated against the local fixture -- real
    sites will likely need this refined as their specific patterns are
    discovered.

    Each candidate element is handled defensively: confirmed on a real
    site (Aviva, a page with cascading dropdowns re-rendering live) that
    an element enumerated at the start of this function can go stale
    (detached from the DOM) by the time it's actually processed a moment
    later, which otherwise hangs for a full Playwright timeout and then
    crashes discovery entirely -- taking every other field on the page
    down with it, the same class of problem already fixed for the actual
    fill step. A field that's mid-re-render right now is fairly treated
    as not currently discoverable rather than a fatal error; the next
    call (the next loop iteration in fill_visible_fields's caller) will
    find it once the page has settled.
    """
    pairs: list[tuple[str, Locator]] = []

    for label in page.locator("label").all():
        try:
            if not label.is_visible():
                # A label a real user can never see is never a legitimate
                # field to fill, regardless of whether its for= target
                # happens to resolve to something with its own layout box --
                # confirmed on a real site (Aviva) as an anti-bot honeypot:
                # a display:none <label class="hp-label" for="...">Previous
                # Insurance Start Date</label> pointing at a tabindex="-1"
                # input that itself passes a naive visibility check. Only a
                # script that fills whatever it can resolve, without ever
                # looking at the label itself, would touch this field.
                continue
            control = _resolve_labeled_control(label)
            if control is None:
                continue
            text = label.inner_text().strip()
            if not text:
                continue
            # Marks the control as already discovered so the aria-label scan
            # below doesn't also pick it up as a second, redundant entry.
            control.evaluate(f"el => el.setAttribute('{_DISCOVERED_MARKER}', '1')")
        except Exception:
            continue
        pairs.append((text, control))

    for group in page.locator('[role="radiogroup"]').all():
        try:
            if not group.is_visible():
                continue

            if group.locator('[role="radio"]').count() == 1:
                # A radiogroup wrapping exactly one radio option is often a
                # fragment of a larger multi-option question split across
                # several sibling radiogroups -- confirmed on a real site
                # (Aviva), where each option ("New", "Used", "Demo under
                # 5,000 kms") gets its own radiogroup, but their shared
                # parent container carries the real question as its own
                # aria-label ("Select the condition your car was in when
                # you got it"). That parent contains every fragment as a
                # descendant, so it works directly as the field's control
                # -- a single click search across it naturally finds
                # whichever option's text matches. The parent is added to
                # pairs once processed so the next sibling fragment doesn't
                # re-add the same question a second (or third) time -- but
                # every fragment's own radio still gets marked discovered
                # on every pass, not just the first: confirmed on a real
                # site (Aviva) that skipping this for later siblings (once
                # the parent's own marker is already set) leaves their own
                # aria-label ("Used", "Demo under 5,000 kms" -- its actual
                # radio options are real <input role="radio" aria-label="...">
                # elements) exposed to being rediscovered a second time as
                # its own spurious standalone field by the own-aria-label
                # pass below, which can then resolve (a bare "Used" label
                # is a plausible enough LLM guess) and fail outright, since
                # clicking-by-text finds nothing inside a bare input with
                # no text content.
                parent = group.locator("xpath=..")
                parent_label = (parent.get_attribute("aria-label") or "").strip()
                if parent_label:
                    group.locator('[role="radio"]').first.evaluate(
                        f"el => el.setAttribute('{_DISCOVERED_MARKER}', '1')"
                    )
                    if parent.get_attribute(_DISCOVERED_MARKER) is None:
                        parent.evaluate(f"el => el.setAttribute('{_DISCOVERED_MARKER}', '1')")
                        pairs.append((parent_label, parent))
                    continue

            text = (group.get_attribute("aria-label") or "").strip()
        except Exception:
            continue
        if text:
            pairs.append((text, group))

    # A control can carry its own aria-label directly, with no separate
    # <label> element pointing at it at all -- confirmed on a real site
    # (Aviva), where the actual Year/Make/Model <select> elements are
    # marked up exactly this way (e.g. aria-label="Select the model of
    # your car", no for=, no wrapping <label>). Without this, those
    # controls were entirely invisible to discovery, regardless of how
    # well the mapping or widget-interaction layers worked.
    aria_label_selector = ", ".join(
        f"{tag}[aria-label]:not([{_DISCOVERED_MARKER}])" for tag in ("input", "select", "textarea")
    )
    for control in page.locator(aria_label_selector).all():
        try:
            if not control.is_visible():
                continue
            text = (control.get_attribute("aria-label") or "").strip()
        except Exception:
            continue
        if text:
            pairs.append((text, control))

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
    page's *visible* text shows a bot-wall indicator -- never attempts to
    work around it, and never fills anything if one is present.

    Checks rendered text (page.inner_text), not page.content() (raw HTML
    source): confirmed against a real saved page that passive/invisible
    reCAPTCHA infrastructure (script tags, a corner badge, a hidden
    response field) makes "recaptcha" appear in the HTML source of nearly
    every modern site regardless of whether any challenge is actually
    being presented. Checking visible text only catches an actual
    human-facing block, not the mere presence of the product.

    A field that resolves and classifies fine can still fail to actually
    interact with at runtime -- confirmed on a real site (Aviva) where a
    mis-resolved label pointed a click at text that was never going to
    appear, hanging for a full Playwright timeout and then crashing the
    entire call, taking every other field on the page down with it. Each
    field's *entire* per-field body is isolated, not just the final
    interaction step -- confirmed on the same real site that widget-type
    detection itself can hit a stale, since-re-rendered element (the page
    keeps mutating during an LLM fallback call's real network latency),
    which crashed just as hard from a step earlier than the original fix
    covered. One bad field can't take the rest of the page down from
    anywhere in its own processing; the failure is recorded in
    failed_to_fill and the loop moves on.
    """
    visible_text = page.inner_text("body")
    if detect_captcha(visible_text):
        raise CaptchaDetected(raw_evidence_text=visible_text)

    report = FillReport()

    for label_text, control in discover_fields(page):
        try:
            path = resolve_field(label_text, llm_fallback=llm_fallback)
            if path is None:
                report.unresolved.append(label_text)
                continue

            widget_type = detect_widget_type(control)
            if widget_type is WidgetType.UNKNOWN:
                report.skipped_unknown_widget.append(label_text)
                continue

            value = get_field_value(intake, path, vehicle_index=vehicle_index, household_index=household_index)
            if value is None:
                # A resolved, classified field with genuinely no data behind
                # it -- confirmed on a real site (Aviva) that leaving this
                # unguarded types the literal string "None" into the page.
                # On a type="number" input that raises outright; on a plain
                # text field it would silently succeed and corrupt the form
                # with garbage instead, which is worse. Reported separately
                # from both "unresolved" (we don't know what this field is)
                # and "failed" (we tried and the interaction itself broke).
                report.no_data[label_text] = path
                continue
            _apply(page, control, widget_type, value)
        except Exception as exc:
            report.failed_to_fill[label_text] = f"{type(exc).__name__}: {exc}"
            continue
        report.filled[label_text] = path

    return report


def _apply(page: Page, control: Locator, widget_type: WidgetType, value: object) -> None:
    if widget_type is WidgetType.TEXT:
        fill_text(control, str(value))
    elif widget_type is WidgetType.NATIVE_SELECT:
        # <option> children exist in the DOM whether or not the select is
        # open, so the display value can be resolved up front.
        select_native(control, resolve_display_value(control, str(value)))
    elif widget_type is WidgetType.CUSTOM_DROPDOWN:
        # NOTE: unlike NATIVE_SELECT/RADIO, a custom dropdown's options
        # often don't exist in the DOM until the trigger is clicked open,
        # so resolve_display_value can't run beforehand the same way --
        # this still passes the raw stored value through. A real
        # stored-vs-displayed mismatch here (the same class of bug this
        # module exists to fix) remains a known gap.
        select_custom_dropdown(page, control, str(value))
    elif widget_type is WidgetType.CHECKBOX:
        set_checkbox(control, bool(value))
    elif widget_type is WidgetType.RADIO:
        click_radio_or_toggle(control, resolve_display_value(control, str(value)))
