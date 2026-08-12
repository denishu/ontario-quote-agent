from quote_agent.agents import extract_quote_from_text, extract_quotes_from_text
from quote_agent.models import Confidence, CoverageConfig


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


def test_extract_quote_from_text_falls_back_to_benchmark_coverage_when_page_shows_none():
    # Confirmed on a real site (MyChoice): a comparison-card view can show
    # only price and underwriter, no coverage breakdown at all -- must
    # fall back to the benchmark rather than the model guessing at
    # numbers that aren't on the page, and confidence must reflect that
    # the coverage match is assumed, not confirmed.
    def fake_extract(page_text: str) -> dict:
        return {"premium_annual": 3198.00, "returned_legal_underwriter": "Wawanesa Mutual"}

    benchmark = make_benchmark(third_party_liability_limit=2_000_000, dcpd_included=True)
    result = extract_quote_from_text("Wawanesa Mutual $266.50/month $3198.00/year", benchmark, llm_extract=fake_extract)

    assert result.premium_annual == 3198.00
    assert result.returned_coverage.third_party_liability_limit == 2_000_000
    assert result.returned_coverage.dcpd_included is True
    assert result.confidence is Confidence.MEDIUM


def test_extract_quote_from_text_uses_high_confidence_when_coverage_is_shown():
    def fake_extract(page_text: str) -> dict:
        return {
            "premium_annual": 1284.00,
            "returned_legal_underwriter": "Belair Insurance Company Inc.",
            "third_party_liability_limit": 1_000_000,
            "dcpd_included": True,
        }

    result = extract_quote_from_text("full breakdown shown", make_benchmark(), llm_extract=fake_extract)

    assert result.confidence is Confidence.HIGH


def test_extract_quotes_from_text_returns_one_quote_obtained_per_underwriter():
    # Mirrors a real MyChoice page exactly: four underwriters, each
    # reached through a broker, no coverage breakdown for any of them.
    def fake_extract_multi(page_text: str) -> dict:
        assert "Brokered by Hub International" in page_text
        return {
            "quotes": [
                {"premium_annual": 3198.00, "premium_monthly": 266.50, "returned_legal_underwriter": "Wawanesa Mutual"},
                {"premium_annual": 3369.00, "premium_monthly": 280.75, "returned_legal_underwriter": "Economical Mutual"},
                {"premium_annual": 3923.00, "premium_monthly": 326.92, "returned_legal_underwriter": "Pembridge"},
                {"premium_annual": 4369.00, "premium_monthly": 364.08, "returned_legal_underwriter": "SGI Canada"},
            ]
        }

    page_text = (
        "Brokered by Hub International\nWawanesa Mutual\n$266.50/month $3198.00/year\n\n"
        "Brokered by Mitch Insurance\nEconomical Mutual\n$280.75/month $3369.00/year"
    )
    results = extract_quotes_from_text(page_text, make_benchmark(), llm_extract=fake_extract_multi)

    assert len(results) == 4
    assert [r.returned_legal_underwriter for r in results] == [
        "Wawanesa Mutual",
        "Economical Mutual",
        "Pembridge",
        "SGI Canada",
    ]
    assert [r.premium_annual for r in results] == [3198.00, 3369.00, 3923.00, 4369.00]
    assert all(r.confidence is Confidence.MEDIUM for r in results)  # none showed a coverage breakdown
    assert all(r.raw_evidence_text == page_text for r in results)


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
