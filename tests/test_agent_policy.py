import pytest

from quote_agent.agents import (
    StopBeforeSensitiveAction,
    TransientAttemptError,
    detect_captcha,
    guard_against_sensitive_action,
    is_sensitive_action,
    run_with_bounded_retry,
)


@pytest.mark.parametrize(
    "label",
    ["Submit", "I Agree", "Pay Now", "Confirm Purchase", "Sign and Continue", "Buy Now", "I consent"],
)
def test_sensitive_action_labels_are_flagged(label):
    assert is_sensitive_action(label)


@pytest.mark.parametrize(
    "label", ["Get Quote", "Continue", "Next", "Calculate My Rate", "See My Price", "Start"]
)
def test_normal_quote_flow_labels_are_not_flagged(label):
    assert not is_sensitive_action(label)


def test_guard_raises_for_sensitive_action():
    with pytest.raises(StopBeforeSensitiveAction):
        guard_against_sensitive_action("Submit Application", raw_evidence_text="<page text>")


def test_guard_does_not_raise_for_normal_action():
    guard_against_sensitive_action("Get Quote", raw_evidence_text="<page text>")


@pytest.mark.parametrize(
    "text",
    [
        "Please complete the CAPTCHA below",
        "verify you are human",
        "Are you a robot?",
        "unusual traffic from your network",
    ],
)
def test_captcha_indicators_are_detected(text):
    assert detect_captcha(text)


def test_normal_page_text_is_not_flagged_as_captcha():
    assert not detect_captcha("Your annual premium is $1,234.56")


def test_bounded_retry_succeeds_on_first_attempt():
    calls = []

    def attempt():
        calls.append(1)
        return "ok"

    assert run_with_bounded_retry(attempt) == "ok"
    assert len(calls) == 1


def test_bounded_retry_retries_once_on_transient_error():
    calls = []

    def attempt():
        calls.append(1)
        if len(calls) == 1:
            raise TransientAttemptError("timeout")
        return "ok"

    assert run_with_bounded_retry(attempt) == "ok"
    assert len(calls) == 2


def test_bounded_retry_propagates_after_second_transient_failure():
    calls = []

    def attempt():
        calls.append(1)
        raise TransientAttemptError("timeout")

    with pytest.raises(TransientAttemptError):
        run_with_bounded_retry(attempt)
    assert len(calls) == 2


def test_bounded_retry_never_retries_non_transient_error():
    calls = []

    def attempt():
        calls.append(1)
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        run_with_bounded_retry(attempt)
    assert len(calls) == 1
