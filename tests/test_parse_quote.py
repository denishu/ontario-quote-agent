from quote_agent.agents import extract_quote_from_text
from quote_agent.models import CoverageConfig


def make_benchmark(**overrides) -> CoverageConfig:
    defaults = dict(
        effective_date="2026-09-01",
        third_party_liability_limit=1_000_000,
        dcpd_included=True,
    )
    defaults.update(overrides)
    return CoverageConfig(**defaults)


def test_extract_quote_from_text_builds_a_matching_quote_obtained():
    # Mirrors a real belairdirect quote-result page's actual shape
    # (price plus a coverage breakdown card, confirmed via screenshot):
    # premium, liability limit, collision/comprehensive deductibles,
    # DCPD, an optional benefit, and a discount.
    def fake_extract(page_text: str) -> dict:
        assert "annual premium" in page_text.lower()
        return {
            "premium_annual": 1284.00,
            "premium_monthly": 107.00,
            "returned_legal_underwriter": "Belair Insurance Company Inc.",
            "third_party_liability_limit": 1_000_000,
            "dcpd_included": True,
            "dcpd_deductible": 0,
            "collision_deductible": 1000,
            "comprehensive_deductible": 1000,
            "all_perils_deductible": None,
            "optional_benefits": {"Rental car protection": "included"},
            "endorsements": [],
            "discounts": [{"name": "Multi-vehicle", "applied": True}],
        }

    result = extract_quote_from_text(
        "Your annual premium is $1,284.00 -- Liability covered up to $1,000,000",
        make_benchmark(),
        llm_extract=fake_extract,
    )

    assert result.premium_annual == 1284.00
    assert result.returned_legal_underwriter == "Belair Insurance Company Inc."
    assert result.returned_coverage.third_party_liability_limit == 1_000_000
    assert result.returned_coverage.dcpd_included is True
    assert result.returned_coverage.dcpd_deductible == 0
    assert result.returned_coverage.collision_deductible == 1000
    assert result.returned_coverage.comprehensive_deductible == 1000
    assert result.returned_coverage.optional_benefits == {"Rental car protection": "included"}
    assert len(result.discounts) == 1
    assert result.discounts[0].name == "Multi-vehicle"
    assert result.discounts[0].applied is True
    # not part of the extraction schema -- carried over from the benchmark
    assert result.returned_coverage.effective_date == "2026-09-01"


def test_extract_quote_from_text_preserves_unextracted_benchmark_fields():
    # effective_date/term_months/telematics_opt_in aren't in the
    # extraction tool's schema at all -- a real quote confirms the terms
    # actually requested rather than re-displaying every one of them, so
    # the honest default for what the page genuinely doesn't show is
    # whatever was asked for.
    def fake_extract(page_text: str) -> dict:
        return {
            "premium_annual": 500.0,
            "returned_legal_underwriter": "Test Insurer",
            "third_party_liability_limit": 2_000_000,
            "dcpd_included": False,
        }

    benchmark = make_benchmark(term_months=12, telematics_opt_in=True)
    result = extract_quote_from_text("some page text", benchmark, llm_extract=fake_extract)

    assert result.returned_coverage.term_months == 12
    assert result.returned_coverage.telematics_opt_in is True
    assert result.returned_coverage.dcpd_included is False
    assert result.returned_coverage.dcpd_deductible is None
    assert result.returned_coverage.optional_benefits == {}
    assert result.returned_coverage.endorsements == []
    assert result.discounts == []


def test_extract_quote_from_text_keeps_the_full_page_text_as_evidence():
    def fake_extract(page_text: str) -> dict:
        return {
            "premium_annual": 500.0,
            "returned_legal_underwriter": "Test Insurer",
            "third_party_liability_limit": 2_000_000,
            "dcpd_included": False,
        }

    result = extract_quote_from_text("the full raw page text", make_benchmark(), llm_extract=fake_extract)

    assert result.raw_evidence_text == "the full raw page text"
