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
from quote_agent.agents.policy import guard_against_sensitive_action, is_sensitive_action
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


def pause_for_human(page: Page, instructions: str, timeout_s: float = 1800.0) -> bool:
    """Print instructions for a human to complete something directly in
    the browser -- a consent checkbox, a submit button automation must
    never click itself -- then wait for the page to actually change
    before resuming. Automation still never performs the sensitive action
    itself; this only stops treating "a human has to act here" as a
    permanent dead end when a human is actually present (headed mode) to
    act. Only meaningful with a real, visible browser window -- calling
    this against a headless page just burns the timeout with no one able
    to respond.

    Returns whether a change was actually observed within timeout_s.
    """
    print(f"\n>>> {instructions}")
    print(">>> Waiting for you to do this in the browser -- I'll resume automatically once the page changes.\n")
    before = _page_fingerprint(page)
    return _wait_for_page_change(page, before, timeout_s=timeout_s)


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
    interactive: bool = False,
) -> FlowResult:
    """Repeatedly fill the current page and click through to the next
    step. Stops when no next-action button is found (a terminal page was
    reached), when clicking didn't produce an observable change, or after
    max_steps -- a bound against looping forever on something unexpected,
    not a claim that a real flow needs exactly that many steps.

    CaptchaDetected (from fill_visible_fields) always propagates to the
    caller regardless of interactive -- a CAPTCHA is a hard stop, no
    exceptions, per the "never bypass, stop, no retry" rule.

    A sensitive next-action is different: the rule that's actually locked
    is "automation must never click buy/sign/declaration/bind itself," not
    "stop forever the moment one is seen." With interactive=False (the
    default -- e.g. an unattended headless run), StopBeforeSensitiveAction
    still raises immediately, since there's no human present to hand off
    to. With interactive=True (a real, visible browser a human is actually
    watching), it pauses instead via pause_for_human() and resumes the
    loop once the human has done it themselves -- automation still never
    performs the sensitive click, it just doesn't treat a human doing
    their own part as a dead end.
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
            if interactive and not fill_report.filled and not fill_report.unresolved:
                # Genuinely nothing left and nothing unresolved -- a real
                # end of form, not a stuck-behind-a-human checkpoint.
                result.steps.append(StepResult(fill_report=fill_report, advanced=False, changed=False))
                break
            if interactive:
                changed = pause_for_human(
                    page,
                    "Nothing left to fill automatically and no safe next-action button was found -- "
                    "this likely needs a human decision (e.g. a consent checkbox). Please complete "
                    "whatever's needed directly in the browser.",
                )
                result.steps.append(StepResult(fill_report=fill_report, advanced=True, changed=changed))
                if not changed:
                    break
                continue
            result.steps.append(StepResult(fill_report=fill_report, advanced=False, changed=False))
            break

        action_label = next_action.inner_text().strip() or "Continue"
        if is_sensitive_action(action_label):
            if not interactive:
                guard_against_sensitive_action(action_label, raw_evidence_text=page.inner_text("body"))
            changed = pause_for_human(
                page,
                f"The next action ('{action_label}') requires a human decision. "
                "Please complete it yourself in the browser.",
            )
            result.steps.append(StepResult(fill_report=fill_report, advanced=True, changed=changed))
            if not changed:
                break
            continue

        before = _page_fingerprint(page)
        next_action.click()
        changed = _wait_for_page_change(page, before)
        result.steps.append(StepResult(fill_report=fill_report, advanced=True, changed=changed))

        if not changed:
            break

    return result
