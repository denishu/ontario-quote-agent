import pytest
from pydantic import ValidationError

from quote_agent.models import (
    Confidence,
    Consent,
    ConsentMode,
    CoverageConfig,
    Evidence,
    QuoteStatus,
    ResultEntry,
)


def make_benchmark() -> CoverageConfig:
    return CoverageConfig(
        effective_date="2026-09-01",
        third_party_liability_limit=2_000_000,
        dcpd_included=True,
        collision_deductible=1000,
        comprehensive_deductible=1000,
        endorsements=["OPCF44R"],
    )


def make_evidence() -> Evidence:
    return Evidence(
        timestamp="2026-08-09T12:00:00Z",
        source_url="https://example.com/quote",
        artifact_ref="evidence/example-001.json",
    )


def test_consent_round_trips_through_json():
    consent = Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE)
    restored = Consent.model_validate_json(consent.model_dump_json())
    assert restored == consent


def test_quoted_result_requires_premium_and_coverage():
    with pytest.raises(ValidationError):
        ResultEntry(
            registry_id="test-001",
            status=QuoteStatus.QUOTED_COMPARABLE,
            evidence=make_evidence(),
            confidence=Confidence.HIGH,
        )


def test_quoted_result_valid_with_premium_and_coverage():
    result = ResultEntry(
        registry_id="test-001",
        status=QuoteStatus.QUOTED_COMPARABLE,
        returned_legal_underwriter="Test Insurance Company",
        premium_annual=1234.56,
        returned_coverage=make_benchmark(),
        evidence=make_evidence(),
        confidence=Confidence.HIGH,
    )
    assert result.coverage_variance == []


def test_quoted_result_requires_returned_legal_underwriter():
    with pytest.raises(ValidationError):
        ResultEntry(
            registry_id="test-001",
            status=QuoteStatus.QUOTED_COMPARABLE,
            premium_annual=1234.56,
            returned_coverage=make_benchmark(),
            evidence=make_evidence(),
            confidence=Confidence.HIGH,
        )


def test_non_quote_result_requires_failure_reason():
    with pytest.raises(ValidationError):
        ResultEntry(
            registry_id="test-002",
            status=QuoteStatus.BLOCKED,
            evidence=make_evidence(),
            confidence=Confidence.LOW,
        )


def test_non_quote_result_valid_with_failure_reason():
    result = ResultEntry(
        registry_id="test-002",
        status=QuoteStatus.BLOCKED,
        evidence=make_evidence(),
        confidence=Confidence.LOW,
        failure_reason="CAPTCHA presented on quote step 3",
        next_action="Retry later or use broker route instead",
    )
    assert result.status is QuoteStatus.BLOCKED
