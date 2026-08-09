from quote_agent.models import Confidence, CoverageConfig, Evidence, QuoteStatus, ResultEntry
from quote_agent.normalize import apply_result_duplicates, find_result_duplicates


def make_coverage() -> CoverageConfig:
    return CoverageConfig(
        effective_date="2026-09-01",
        third_party_liability_limit=2_000_000,
        dcpd_included=True,
    )


def make_evidence(ref: str) -> Evidence:
    return Evidence(timestamp="2026-08-09T12:00:00Z", source_url="https://example.com", artifact_ref=ref)


def make_quote(registry_id: str, underwriter: str, premium: float = 1000.0) -> ResultEntry:
    return ResultEntry(
        registry_id=registry_id,
        status=QuoteStatus.QUOTED_COMPARABLE,
        returned_legal_underwriter=underwriter,
        premium_annual=premium,
        returned_coverage=make_coverage(),
        evidence=make_evidence(f"evidence/{registry_id}.json"),
        confidence=Confidence.HIGH,
    )


def test_no_duplicates_when_underwriters_differ():
    results = [
        make_quote("intact-direct", "Intact Insurance Company"),
        make_quote("aviva-direct", "Aviva Insurance Company of Canada"),
    ]
    report = find_result_duplicates(results)
    assert report.duplicates == {}


def test_distinct_group_entities_are_not_merged():
    # Two genuinely different legal entities within the same "Aviva" group —
    # must never be flagged as duplicates of each other.
    results = [
        make_quote("aviva-direct", "Aviva Insurance Company of Canada"),
        make_quote("aviva-broker", "Aviva General Insurance Company"),
    ]
    report = find_result_duplicates(results)
    assert report.duplicates == {}


def test_exact_underwriter_match_is_flagged_as_duplicate():
    results = [
        make_quote("intact-direct", "Intact Insurance Company"),
        make_quote("mychoice-aggregator", "Intact Insurance Company"),
    ]
    report = find_result_duplicates(results)
    assert "mychoice-aggregator" in report.duplicates
    assert "intact-direct" in report.duplicates["mychoice-aggregator"]
    assert "intact-direct" not in report.duplicates


def test_normalization_handles_case_and_whitespace_only():
    results = [
        make_quote("intact-direct", "Intact Insurance Company"),
        make_quote("mychoice-aggregator", "  intact insurance company  "),
    ]
    report = find_result_duplicates(results)
    assert "mychoice-aggregator" in report.duplicates


def test_formatting_variant_is_not_caught_known_limitation():
    # "Co." vs "Company" is a real known limitation of exact-match dedup —
    # this test documents that it is NOT caught, on purpose.
    results = [
        make_quote("a", "Aviva Insurance Co. of Canada"),
        make_quote("b", "Aviva Insurance Company of Canada"),
    ]
    report = find_result_duplicates(results)
    assert report.duplicates == {}


def test_apply_result_duplicates_preserves_premium_and_coverage():
    results = [
        make_quote("intact-direct", "Intact Insurance Company", premium=1200.0),
        make_quote("mychoice-aggregator", "Intact Insurance Company", premium=1150.0),
    ]
    report = find_result_duplicates(results)
    updated = apply_result_duplicates(results, report)

    primary, duplicate = updated
    assert primary.status is QuoteStatus.QUOTED_COMPARABLE
    assert duplicate.status is QuoteStatus.DUPLICATE_RATE_SOURCE
    assert duplicate.premium_annual == 1150.0  # preserved, not discarded
    assert duplicate.returned_coverage is not None
    assert duplicate.failure_reason is not None and "intact-direct" in duplicate.failure_reason
