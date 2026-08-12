"""Redacted screenshot capture -- the visual counterpart to
evidence.redact.redact_text, for the "redacted screenshot" evidence
artifact the challenge brief names explicitly.

Text redaction works by substituting known sensitive *values* after the
fact; that approach doesn't transfer to an image, since there's no way
to reliably find and black out a value's pixels once they're already
rendered. Masking instead happens *before* the screenshot is ever taken:
every currently-discoverable field this codebase already knows maps to a
sensitive schema path gets covered with an opaque overlay first. There is
no version of the file on disk that ever had real sensitive data visible
in it.

Uses the exact same field-resolution path (discover_fields +
resolve_field) that decides what gets filled elsewhere in this codebase,
against the exact same sensitive-path list format_fill_report uses for
text redaction (mapping.sensitive) -- "sensitive" means one thing across
the whole codebase, not a second, potentially-diverging definition here.
"""

from pathlib import Path
from typing import Callable

from playwright.sync_api import Locator, Page

from quote_agent.agents.loop import discover_fields
from quote_agent.mapping import resolve_field
from quote_agent.mapping.sensitive import is_sensitive_path

_MASK_ATTR = "data-qa-agent-mask"


def _mask_element(page: Page, control: Locator) -> bool:
    """Overlay an opaque, fixed-position div exactly over `control`'s
    current on-screen position. Returns whether a mask was actually
    placed -- False if the control has no visible bounding box right now
    (already hidden, detached, or off-screen), the same "not currently
    discoverable" case discover_fields treats as a non-error elsewhere.
    """
    box = control.bounding_box()
    if box is None:
        return False
    page.evaluate(
        f"""(box) => {{
            const mask = document.createElement('div');
            mask.setAttribute('{_MASK_ATTR}', '1');
            mask.style.position = 'fixed';
            mask.style.left = box.x + 'px';
            mask.style.top = box.y + 'px';
            mask.style.width = box.width + 'px';
            mask.style.height = box.height + 'px';
            mask.style.background = '#000';
            mask.style.zIndex = '2147483647';
            mask.style.pointerEvents = 'none';
            document.body.appendChild(mask);
        }}""",
        box,
    )
    return True


def capture_redacted_screenshot(
    page: Page,
    path: Path,
    *,
    llm_fallback: Callable[[str], str | None] | None = None,
) -> None:
    """Mask every currently-discoverable sensitive field, then screenshot
    the page to `path`.

    A field this pass doesn't discover -- e.g. one behind a modal, not
    yet rendered, or a labeling pattern discover_fields doesn't handle --
    can't be masked. That's the same limitation discover_fields already
    has everywhere else it's used in this codebase, not a new gap
    introduced here; it isn't a substitute for reviewing evidence before
    it leaves your machine.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    for label, control in discover_fields(page):
        field_path = resolve_field(label, llm_fallback=llm_fallback)
        if field_path is not None and is_sensitive_path(field_path):
            _mask_element(page, control)
    page.screenshot(path=str(path))
