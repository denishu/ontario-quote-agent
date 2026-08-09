from quote_agent.models import Confidence, CoverageConfig, Evidence, QuoteStatus, ResultEntry
from quote_agent.normalize import apply_avoided_underwriter_results, find_avoided_underwriter_results


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


def test_no_avoidance_when_underwriter_not_on_list():
    results = [make_quote("td-direct", "TD General Insurance Company")]
    report = find_avoided_underwriter_results(results, avoided_underwriters=["Aviva Insurance Company of Canada"])
    assert report.avoided == {}


def test_direct_route_to_avoided_underwriter_is_flagged():
    results = [make_quote("aviva-direct", "Aviva Insurance Company of Canada")]
    report = find_avoided_underwriter_results(results, avoided_underwriters=["Aviva Insurance Company of Canada"])
    assert "aviva-direct" in report.avoided
    assert "Aviva Insurance Company of Canada" in report.avoided["aviva-direct"]


def test_aggregator_resolving_to_avoided_underwriter_is_flagged():
    # An aggregator doesn't announce its underlying carrier until a quote
    # comes back -- the whole reason this check has to run post-hoc.
    results = [make_quote("mychoice-aggregator", "Aviva Insurance Company of Canada")]
    report = find_avoided_underwriter_results(results, avoided_underwriters=["Aviva Insurance Company of Canada"])
    assert "mychoice-aggregator" in report.avoided


def test_case_and_whitespace_insensitive_match():
    results = [make_quote("mychoice-aggregator", "  aviva insurance company of canada  ")]
    report = find_avoided_underwriter_results(results, avoided_underwriters=["Aviva Insurance Company of Canada"])
    assert "mychoice-aggregator" in report.avoided


def test_distinct_underwriter_in_same_group_is_not_flagged():
    # Aviva General Insurance Company is a different legal entity within
    # the same Aviva group -- must not be swept in just because it's related.
    results = [make_quote("aviva-broker", "Aviva General Insurance Company")]
    report = find_avoided_underwriter_results(results, avoided_underwriters=["Aviva Insurance Company of Canada"])
    assert report.avoided == {}


def test_apply_avoided_underwriter_results_preserves_premium():
    results = [make_quote("aviva-direct", "Aviva Insurance Company of Canada", premium=1150.0)]
    report = find_avoided_underwriter_results(results, avoided_underwriters=["Aviva Insurance Company of Canada"])
    updated = apply_avoided_underwriter_results(results, report)

    (flagged,) = updated
    assert flagged.status is QuoteStatus.INELIGIBLE
    assert flagged.premium_annual == 1150.0  # preserved, not discarded
    assert flagged.failure_reason is not None and "applicant preference" in flagged.failure_reason
