from quote_agent.models import CoverageConfig, QuoteStatus
from quote_agent.normalize import classify_quote, diff_coverage


def make_benchmark(**overrides) -> CoverageConfig:
    base = dict(
        effective_date="2026-09-01",
        third_party_liability_limit=2_000_000,
        dcpd_included=True,
        collision_deductible=1000,
        comprehensive_deductible=1000,
        endorsements=["OPCF44R"],
        optional_benefits={"income_replacement": "included"},
    )
    base.update(overrides)
    return CoverageConfig(**base)


def test_identical_coverage_is_comparable_with_no_variance():
    benchmark = make_benchmark()
    returned = make_benchmark()
    status, variance = classify_quote(benchmark, returned)
    assert status is QuoteStatus.QUOTED_COMPARABLE
    assert variance == []


def test_differing_deductible_is_non_comparable():
    benchmark = make_benchmark()
    returned = make_benchmark(collision_deductible=500)
    status, variance = classify_quote(benchmark, returned)
    assert status is QuoteStatus.QUOTED_NON_COMPARABLE
    assert variance == ["collision_deductible"]


def test_differing_optional_benefit_is_flagged_by_name():
    benchmark = make_benchmark()
    returned = make_benchmark(optional_benefits={"income_replacement": "excluded"})
    variance = diff_coverage(benchmark, returned)
    assert variance == ["optional_benefits.income_replacement"]


def test_missing_optional_benefit_key_counts_as_variance():
    benchmark = make_benchmark(optional_benefits={"income_replacement": "included", "caregiver": "included"})
    returned = make_benchmark(optional_benefits={"income_replacement": "included"})
    variance = diff_coverage(benchmark, returned)
    assert variance == ["optional_benefits.caregiver"]


def test_differing_endorsements_set_is_flagged():
    benchmark = make_benchmark(endorsements=["OPCF44R"])
    returned = make_benchmark(endorsements=["OPCF44R", "OPCF20"])
    variance = diff_coverage(benchmark, returned)
    assert variance == ["endorsements"]


def test_multiple_differences_are_all_reported_and_sorted():
    benchmark = make_benchmark()
    returned = make_benchmark(collision_deductible=500, third_party_liability_limit=1_000_000)
    variance = diff_coverage(benchmark, returned)
    assert variance == ["collision_deductible", "third_party_liability_limit"]
