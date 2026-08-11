"""Multi-step orchestration: repeatedly fill the current page's fields
(fill_visible_fields) and click through to the next step, until a
terminal page is reached, a sensitive action stops it, or a bounded step
limit is hit.

Deliberately doesn't try to detect whether a terminal page is an actual
quote versus something else (an error page, a dead end) -- that's a
separate concern (LLM-assisted quote-result parsing) that comes after
this loop stops, not part of it.
"""

from dataclasses import dataclass, field
from typing import Callable

from playwright.sync_api import Locator, Page

from quote_agent.agents.loop import FillReport, discover_fields, fill_visible_fields
from quote_agent.agents.policy import guard_against_sensitive_action
from quote_agent.models import IntakeProfile

_NEXT_ACTION_KEYWORDS = (
    "continue",
    "next",
    "get quote",
    "get my quote",
    "get quotes",
    "submit",
    "proceed",
)


def find_next_action(page: Page) -> Locator | None:
    """Find whatever button/link progresses the current step: a
    type="submit" control first, falling back to common progression text.
    Skips anything not currently visible, since a hidden later step's
    button can exist in the DOM without being the one to click. Heuristic,
    like widget-type detection -- real sites may need this refined once
    their exact button text and structure are known.
    """
    submit_controls = page.locator('button[type="submit"], input[type="submit"]')
    for i in range(submit_controls.count()):
        candidate = submit_controls.nth(i)
        if candidate.is_visible():
            return candidate

    for keyword in _NEXT_ACTION_KEYWORDS:
        for role in ("button", "link"):
            candidates = page.get_by_role(role, name=keyword, exact=False)
            for i in range(candidates.count()):
                candidate = candidates.nth(i)
                if candidate.is_visible():
                    return candidate

    return None


def _page_fingerprint(page: Page) -> tuple[str, tuple[str, ...]]:
    """A cheap signal for "has the page meaningfully changed": the current
    URL plus the set of currently-visible field labels.
    """
    labels = tuple(sorted(label for label, _ in discover_fields(page)))
    return page.url, labels


def _wait_for_page_change(
    page: Page,
    before: tuple[str, tuple[str, ...]],
    timeout_s: float = 10.0,
    poll_interval_s: float = 0.25,
) -> bool:
    """Poll (via Playwright's own wait, not a blocking sleep) until the
    page's fingerprint differs from `before`, or timeout_s elapses.
    Returns whether a change was actually observed.
    """
    elapsed = 0.0
    while elapsed < timeout_s:
        if _page_fingerprint(page) != before:
            return True
        page.wait_for_timeout(poll_interval_s * 1000)
        elapsed += poll_interval_s
    return _page_fingerprint(page) != before


@dataclass
class StepResult:
    fill_report: FillReport
    advanced: bool  # a next-action button was found and clicked
    changed: bool  # the page actually appeared to change afterward


@dataclass
class FlowResult:
    steps: list[StepResult] = field(default_factory=list)


def run_flow_steps(
    page: Page,
    intake: IntakeProfile,
    *,
    max_steps: int = 15,
    vehicle_index: int = 0,
    household_index: int = 0,
    llm_fallback: Callable[[str], str | None] | None = None,
) -> FlowResult:
    """Repeatedly fill the current page and click through to the next
    step. Stops when no next-action button is found (a terminal page was
    reached), when clicking didn't produce an observable change, or after
    max_steps -- a bound against looping forever on something unexpected,
    not a claim that a real flow needs exactly that many steps.

    CaptchaDetected (from fill_visible_fields) and StopBeforeSensitiveAction
    (from guard_against_sensitive_action, when the next-action button
    itself looks sensitive) both propagate to the caller rather than being
    caught here -- run_web_attempt is what turns those into the right
    terminal status.
    """
    result = FlowResult()

    for _ in range(max_steps):
        fill_report = fill_visible_fields(
            page,
            intake,
            vehicle_index=vehicle_index,
            household_index=household_index,
            llm_fallback=llm_fallback,
        )

        next_action = find_next_action(page)
        if next_action is None:
            result.steps.append(StepResult(fill_report=fill_report, advanced=False, changed=False))
            break

        action_label = next_action.inner_text().strip() or "Continue"
        guard_against_sensitive_action(action_label, raw_evidence_text=page.content())

        before = _page_fingerprint(page)
        next_action.click()
        changed = _wait_for_page_change(page, before)
        result.steps.append(StepResult(fill_report=fill_report, advanced=True, changed=changed))

        if not changed:
            break

    return result
