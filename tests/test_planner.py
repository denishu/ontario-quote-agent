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
    RegistryEntry,
)
from quote_agent.planner import plan_routes


def make_intake(**consent_overrides) -> IntakeProfile:
    consent_defaults = dict(
        timestamp="2026-08-09T09:00:00Z",
        mode=ConsentMode.LIVE_QUOTE,
    )
    consent_defaults.update(consent_overrides)
    return IntakeProfile(
        consent=Consent(**consent_defaults),
        identity=Identity(legal_name="Test Applicant", date_of_birth="1990-01-01"),
        contact_email="test@example.com",
        contact_phone="555-555-5555",
        address=Address(street="1 Test St", city="Toronto", postal_code="M1M 1M1"),
        vehicles=[],
        insurance_history=InsuranceHistory(),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01",
            third_party_liability_limit=2_000_000,
            dcpd_included=True,
        ),
    )


def make_entry(
    registry_id: str,
    distribution_type: DistributionType = DistributionType.DIRECT,
    distinct_rate_source_id: str | None = None,
) -> RegistryEntry:
    return RegistryEntry(
        registry_id=registry_id,
        last_verified_at="2026-08-09T00:00:00Z",
        legal_underwriter=f"{registry_id} Underwriter",
        insurer_group=f"{registry_id} Group",
        brand_or_program=registry_id,
        distribution_type=distribution_type,
        product_scope=ProductScope.STANDARD_PPA,
        distinct_rate_source_id=distinct_rate_source_id or registry_id,
    )


def test_empty_permitted_channels_allows_every_distribution_type():
    intake = make_intake(permitted_channels=[])
    registry = [make_entry("a", DistributionType.DIRECT), make_entry("b", DistributionType.BROKER)]
    plan = plan_routes(intake, registry)
    assert {e.registry_id for e in plan.to_attempt} == {"a", "b"}
    assert plan.excluded == {}


def test_permitted_channels_filters_out_other_distribution_types():
    intake = make_intake(permitted_channels=[DistributionType.DIRECT])
    registry = [make_entry("a", DistributionType.DIRECT), make_entry("b", DistributionType.BROKER)]
    plan = plan_routes(intake, registry)
    assert [e.registry_id for e in plan.to_attempt] == ["a"]
    assert "b" in plan.excluded


def test_excluded_source_ids_wins_over_approved_source_ids():
    intake = make_intake(approved_source_ids=["a"], excluded_source_ids=["a"])
    registry = [make_entry("a")]
    plan = plan_routes(intake, registry)
    assert plan.to_attempt == []
    assert plan.excluded["a"] == "excluded by consent.excluded_source_ids"


def test_approved_source_ids_restricts_to_allowlist():
    intake = make_intake(approved_source_ids=["a"])
    registry = [make_entry("a"), make_entry("b")]
    plan = plan_routes(intake, registry)
    assert [e.registry_id for e in plan.to_attempt] == ["a"]
    assert plan.excluded["b"] == "not in consent.approved_source_ids"


def test_duplicate_rate_source_collapses_to_first_seen():
    intake = make_intake()
    registry = [
        make_entry("direct-brand", distinct_rate_source_id="shared-underwriter"),
        make_entry("broker-panel", distinct_rate_source_id="shared-underwriter"),
    ]
    plan = plan_routes(intake, registry)
    assert [e.registry_id for e in plan.to_attempt] == ["direct-brand"]
    assert "shared-underwriter" in plan.excluded["broker-panel"]
