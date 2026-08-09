"""Safety and retry primitives shared by every site-specific web flow.

These are deliberately technology-agnostic — nothing here imports
Playwright. A flow calls guard_against_sensitive_action() before any click
and can check detect_captcha() against whatever page text it has; the
orchestrator in web.py enforces the bounded-retry policy around the whole
attempt.
"""

from typing import Callable, TypeVar

T = TypeVar("T")


class CaptchaDetected(Exception):
    """A CAPTCHA or other anti-automation barrier was presented. Terminal —
    never evaded, never retried.
    """

    def __init__(self, raw_evidence_text: str):
        super().__init__("CAPTCHA or anti-automation barrier detected")
        self.raw_evidence_text = raw_evidence_text


class StopBeforeSensitiveAction(Exception):
    """The flow was about to cross a checkpoint that requires a human —
    submit, pay, sign, consent, or an identity lookup. Terminal — never
    retried, never proceeded past automatically.
    """

    def __init__(self, raw_evidence_text: str, reason: str):
        super().__init__(reason)
        self.raw_evidence_text = raw_evidence_text
        self.reason = reason


class TransientAttemptError(Exception):
    """A genuine transient technical failure (timeout, connection reset).
    The only exception type eligible for a retry, and only once.
    """


_SENSITIVE_ACTION_KEYWORDS = (
    "submit",
    "i agree",
    "accept and continue",
    "accept terms",
    "pay",
    "confirm purchase",
    "buy now",
    "checkout",
    "sign",
    "declare",
    "consent",
    "purchase",
    "bind",
)


def is_sensitive_action(label: str) -> bool:
    """True if an action label (button text, link text) looks like it
    would cross one of the brief's hard stops: an application declaration,
    payment, signature, consent, or purchase step.

    Deliberately broad: over-triggering costs an unnecessary
    manual_handoff, under-triggering risks accidentally binding a policy
    or submitting payment. The former is the acceptable failure mode.
    """
    normalized = label.strip().casefold()
    return any(keyword in normalized for keyword in _SENSITIVE_ACTION_KEYWORDS)


def guard_against_sensitive_action(label: str, raw_evidence_text: str) -> None:
    """Raise StopBeforeSensitiveAction if `label` looks like a checkpoint a
    flow should never cross automatically. A site-specific flow should
    call this before performing any click.
    """
    if is_sensitive_action(label):
        raise StopBeforeSensitiveAction(
            raw_evidence_text=raw_evidence_text,
            reason=f"Stopped before action '{label}' — requires a human checkpoint per policy",
        )


_CAPTCHA_INDICATORS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "verify you are human",
    "are you a robot",
    "unusual traffic",
    "automated queries",
    "prove you're not a robot",
)


def detect_captcha(page_text: str) -> bool:
    """True if page_text contains a common CAPTCHA / bot-wall indicator.
    Heuristic, not exhaustive — a site with a barrier that doesn't use any
    of these phrases won't be caught, and that's a known limitation rather
    than something worth chasing exhaustively.
    """
    normalized = page_text.casefold()
    return any(indicator in normalized for indicator in _CAPTCHA_INDICATORS)


def run_with_bounded_retry(attempt: Callable[[], T]) -> T:
    """Exactly one attempt, plus exactly one retry — and only for a
    TransientAttemptError. Any other exception (including
    CaptchaDetected/StopBeforeSensitiveAction) propagates immediately on
    the first attempt, per the bounded-attempt policy: never retry a
    rejection, CAPTCHA, or terms block.
    """
    try:
        return attempt()
    except TransientAttemptError:
        return attempt()
