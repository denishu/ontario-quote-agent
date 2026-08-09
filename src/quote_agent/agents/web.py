"""The generic shell around one web attempt.

A site-specific flow (not built yet — there's no source list to write one
against) is just a callable: it takes the intake profile, drives whatever
Playwright interaction the site needs, and returns a QuoteObtained or
NonQuoteOutcome, or raises one of the policy signals in policy.py.
run_web_attempt() wraps that callable with the bounded-retry policy, turns
every safety signal or unexpected error into the right terminal status, and
always produces a valid, evidence-backed ResultEntry — never an unhandled
crash, never a silently dropped attempt.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from quote_agent.agents.policy import (
    CaptchaDetected,
    StopBeforeSensitiveAction,
    TransientAttemptError,
    run_with_bounded_retry,
)
from quote_agent.evidence import save_evidence
from quote_agent.models import (
    Confidence,
    CoverageConfig,
    Discount,
    Evidence,
    IntakeProfile,
    RegistryEntry,
    ResultEntry,
)
from quote_agent.models.status import QuoteStatus
from quote_agent.normalize import classify_quote


@dataclass
class QuoteObtained:
    """A flow reports this when a site returned an actual quote."""

    raw_evidence_text: str
    premium_annual: float
    returned_coverage: CoverageConfig
    returned_legal_underwriter: str
    discounts: list[Discount] = field(default_factory=list)
    confidence: Confidence = Confidence.HIGH


@dataclass
class NonQuoteOutcome:
    """A flow (or the orchestrator, mapping a caught exception) reports
    this for any terminal status that isn't a quote.
    """

    status: QuoteStatus
    raw_evidence_text: str
    failure_reason: str
    next_action: str
    confidence: Confidence = Confidence.LOW


WebFlow = Callable[[IntakeProfile], QuoteObtained | NonQuoteOutcome]


def build_result(
    entry: RegistryEntry,
    intake: IntakeProfile,
    outcome: QuoteObtained | NonQuoteOutcome,
    evidence_dir: Path | None = None,
) -> ResultEntry:
    """Turn a flow's outcome into a validated ResultEntry: capture redacted
    evidence, and — for a real quote — run it through the deterministic
    coverage normalizer to decide quoted_comparable vs
    quoted_non_comparable.
    """
    artifact_ref = save_evidence(
        entry.registry_id, outcome.raw_evidence_text, intake, evidence_dir=evidence_dir
    )
    evidence = Evidence(
        timestamp=datetime.now(timezone.utc).isoformat(),
        source_url=entry.quote_url,
        public_phone_route=entry.public_phone_route,
        artifact_ref=artifact_ref,
    )

    if isinstance(outcome, QuoteObtained):
        status, variance = classify_quote(intake.coverage_benchmark, outcome.returned_coverage)
        return ResultEntry(
            registry_id=entry.registry_id,
            status=status,
            returned_legal_underwriter=outcome.returned_legal_underwriter,
            premium_annual=outcome.premium_annual,
            returned_coverage=outcome.returned_coverage,
            coverage_variance=variance,
            discounts=outcome.discounts,
            evidence=evidence,
            confidence=outcome.confidence,
        )

    return ResultEntry(
        registry_id=entry.registry_id,
        status=outcome.status,
        evidence=evidence,
        confidence=outcome.confidence,
        failure_reason=outcome.failure_reason,
        next_action=outcome.next_action,
    )


def run_web_attempt(
    entry: RegistryEntry,
    intake: IntakeProfile,
    flow: WebFlow,
    evidence_dir: Path | None = None,
) -> ResultEntry:
    """The generic orchestrator: enforce the bounded-retry policy, catch
    every safety-relevant signal a flow can raise, and always return a
    valid ResultEntry.
    """
    try:
        outcome: QuoteObtained | NonQuoteOutcome = run_with_bounded_retry(lambda: flow(intake))
    except CaptchaDetected as exc:
        outcome = NonQuoteOutcome(
            status=QuoteStatus.BLOCKED,
            raw_evidence_text=exc.raw_evidence_text,
            failure_reason="CAPTCHA or anti-automation barrier presented; stopped without evading",
            next_action="Retry manually later, or route through a licensed intermediary instead",
        )
    except StopBeforeSensitiveAction as exc:
        outcome = NonQuoteOutcome(
            status=QuoteStatus.MANUAL_HANDOFF,
            raw_evidence_text=exc.raw_evidence_text,
            failure_reason=exc.reason,
            next_action="Applicant must complete this step manually",
        )
    except TransientAttemptError as exc:
        outcome = NonQuoteOutcome(
            status=QuoteStatus.UNREACHABLE,
            raw_evidence_text=f"Attempt failed after one retry: {exc}",
            failure_reason=f"Transient technical error persisted through the bounded retry: {exc}",
            next_action="Retry in a later run",
        )
    except Exception as exc:  # deliberate catch-all: one bad flow must not crash the whole batch
        outcome = NonQuoteOutcome(
            status=QuoteStatus.UNRESOLVED,
            raw_evidence_text=f"Unexpected error: {exc}",
            failure_reason=f"Unhandled error during attempt: {exc!r}",
            next_action="Needs manual investigation",
        )

    return build_result(entry, intake, outcome, evidence_dir=evidence_dir)
