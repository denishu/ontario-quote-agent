from pathlib import Path

from quote_agent.agents import (
    CaptchaDetected,
    NonQuoteOutcome,
    QuoteObtained,
    StopBeforeSensitiveAction,
    TransientAttemptError,
    run_web_attempt,
)
from quote_agent.models import (
    Address,
    Consent,
    ConsentMode,
    CoverageConfig,
    DistributionType,
    Identity,
    InsuranceHistory,
    IntakeProfile,
    ProductScope,
    QuoteStatus,
    RegistryEntry,
)


def make_intake() -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(legal_name="Jane Applicant", date_of_birth="1990-01-01"),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        address=Address(street="123 Main St", city="Toronto", postal_code="M5V 3A8"),
        vehicles=[],
        insurance_history=InsuranceHistory(),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01",
            third_party_liability_limit=2_000_000,
            dcpd_included=True,
            collision_deductible=1000,
        ),
    )


def make_entry(registry_id: str = "aviva-direct") -> RegistryEntry:
    return RegistryEntry(
        registry_id=registry_id,
        last_verified_at="2026-08-09T00:00:00Z",
        legal_underwriter="Aviva Insurance Company of Canada",
        insurer_group="Aviva",
        brand_or_program="Aviva Direct",
        distribution_type=DistributionType.DIRECT,
        product_scope=ProductScope.STANDARD_PPA,
        distinct_rate_source_id=registry_id,
        quote_url="https://example.com/quote",
    )


def test_successful_quote_produces_quoted_comparable_result(tmp_path: Path):
    intake = make_intake()

    def flow(profile):
        return QuoteObtained(
            raw_evidence_text="Your annual premium is $1,234.56 for Jane Applicant",
            premium_annual=1234.56,
            returned_coverage=profile.coverage_benchmark,
            returned_legal_underwriter="Aviva Insurance Company of Canada",
        )

    result = run_web_attempt(make_entry(), intake, flow, evidence_dir=tmp_path)
    assert result.status is QuoteStatus.QUOTED_COMPARABLE
    assert result.premium_annual == 1234.56

    artifact_path = tmp_path / result.evidence.artifact_ref.removeprefix("evidence/")
    assert "Jane Applicant" not in artifact_path.read_text(encoding="utf-8")


def test_quote_with_different_coverage_is_non_comparable(tmp_path: Path):
    intake = make_intake()
    different_coverage = intake.coverage_benchmark.model_copy(update={"collision_deductible": 500})

    def flow(profile):
        return QuoteObtained(
            raw_evidence_text="quote text",
            premium_annual=999.0,
            returned_coverage=different_coverage,
            returned_legal_underwriter="Aviva Insurance Company of Canada",
        )

    result = run_web_attempt(make_entry(), intake, flow, evidence_dir=tmp_path)
    assert result.status is QuoteStatus.QUOTED_NON_COMPARABLE
    assert "collision_deductible" in result.coverage_variance


def test_captcha_maps_to_blocked(tmp_path: Path):
    def flow(profile):
        raise CaptchaDetected(raw_evidence_text="Please complete the CAPTCHA")

    result = run_web_attempt(make_entry(), make_intake(), flow, evidence_dir=tmp_path)
    assert result.status is QuoteStatus.BLOCKED
    assert result.failure_reason is not None


def test_sensitive_action_maps_to_manual_handoff(tmp_path: Path):
    def flow(profile):
        raise StopBeforeSensitiveAction(raw_evidence_text="Submit Application page", reason="about to submit")

    result = run_web_attempt(make_entry(), make_intake(), flow, evidence_dir=tmp_path)
    assert result.status is QuoteStatus.MANUAL_HANDOFF


def test_transient_error_retries_then_succeeds(tmp_path: Path):
    intake = make_intake()
    calls = []

    def flow(profile):
        calls.append(1)
        if len(calls) == 1:
            raise TransientAttemptError("timeout")
        return QuoteObtained(
            raw_evidence_text="quote text",
            premium_annual=1000.0,
            returned_coverage=profile.coverage_benchmark,
            returned_legal_underwriter="Aviva Insurance Company of Canada",
        )

    result = run_web_attempt(make_entry(), intake, flow, evidence_dir=tmp_path)
    assert result.status is QuoteStatus.QUOTED_COMPARABLE
    assert len(calls) == 2


def test_persistent_transient_error_maps_to_unreachable(tmp_path: Path):
    def flow(profile):
        raise TransientAttemptError("timeout")

    result = run_web_attempt(make_entry(), make_intake(), flow, evidence_dir=tmp_path)
    assert result.status is QuoteStatus.UNREACHABLE


def test_summarize_replaces_the_flows_own_failure_reason(tmp_path: Path):
    # summarize is injected the same way resolve_field's llm_fallback is --
    # optional, defaulting to None so no test here needs network access or
    # an API key. When given, it takes over failure_reason entirely rather
    # than the flow's own hand-written string, generated from the actual
    # raw_evidence_text instead.
    def flow(profile):
        raise CaptchaDetected(raw_evidence_text="Please complete the CAPTCHA challenge to continue")

    def fake_summarize(status, raw_evidence_text):
        assert status is QuoteStatus.BLOCKED
        assert "CAPTCHA challenge" in raw_evidence_text
        return "Site presented a CAPTCHA challenge before any form fields were reachable."

    result = run_web_attempt(make_entry(), make_intake(), flow, evidence_dir=tmp_path, summarize=fake_summarize)

    assert result.failure_reason == "Site presented a CAPTCHA challenge before any form fields were reachable."


def test_no_summarize_keeps_the_flows_own_failure_reason(tmp_path: Path):
    def flow(profile):
        raise CaptchaDetected(raw_evidence_text="Please complete the CAPTCHA")

    result = run_web_attempt(make_entry(), make_intake(), flow, evidence_dir=tmp_path)

    assert result.failure_reason == "CAPTCHA or anti-automation barrier presented; stopped without evading"


def test_unexpected_error_maps_to_unresolved_without_crashing(tmp_path: Path):
    def flow(profile):
        raise RuntimeError("something unexpected")

    result = run_web_attempt(make_entry(), make_intake(), flow, evidence_dir=tmp_path)
    assert result.status is QuoteStatus.UNRESOLVED
