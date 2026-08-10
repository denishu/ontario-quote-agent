import pytest

from quote_agent.mapping import get_field_value
from quote_agent.models import (
    AccidentRecord,
    Address,
    Consent,
    ConsentMode,
    ConvictionRecord,
    CoverageConfig,
    HouseholdMember,
    Identity,
    InsuranceHistory,
    IntakeProfile,
    Vehicle,
)


def make_intake(legal_name: str = "Jane Q Applicant") -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(legal_name=legal_name, date_of_birth="1990-01-01"),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        address=Address(street="123 Main St", city="Toronto", postal_code="M5V 3A8"),
        household=[
            HouseholdMember(name="Household One", relationship="parent", licensed=True),
            HouseholdMember(name="Household Two", relationship="sibling", licensed=False),
        ],
        vehicles=[
            Vehicle(
                vin="VIN0",
                model_year=2020,
                make="Toyota",
                model="Corolla",
                ownership="owned",
                primary_use="commute",
                annual_km=12000,
            ),
            Vehicle(
                vin="VIN1",
                model_year=2018,
                make="Honda",
                model="Civic",
                ownership="leased",
                primary_use="pleasure",
                annual_km=8000,
            ),
        ],
        insurance_history=InsuranceHistory(
            accidents_last_6_years=[AccidentRecord(date="2022-01-01", description="fender bender")],
            convictions_last_3_years=[
                ConvictionRecord(date="2024-01-01", description="speeding"),
                ConvictionRecord(date="2024-06-01", description="speeding again"),
            ],
        ),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01", third_party_liability_limit=2_000_000, dcpd_included=True
        ),
    )


def test_simple_attribute_path():
    intake = make_intake()
    assert get_field_value(intake, "identity.date_of_birth") == "1990-01-01"
    assert get_field_value(intake, "address.postal_code") == "M5V 3A8"


def test_nested_coverage_benchmark_path():
    intake = make_intake()
    assert get_field_value(intake, "coverage_benchmark.third_party_liability_limit") == 2_000_000


def test_virtual_first_and_last_name_split():
    intake = make_intake("Jane Q Applicant")
    assert get_field_value(intake, "identity.first_name") == "Jane"
    assert get_field_value(intake, "identity.last_name") == "Q Applicant"


def test_virtual_last_name_is_empty_for_single_word_name():
    intake = make_intake("Cher")
    assert get_field_value(intake, "identity.first_name") == "Cher"
    assert get_field_value(intake, "identity.last_name") == ""


def test_vehicle_fields_use_index_default_zero():
    intake = make_intake()
    assert get_field_value(intake, "vehicles[].make") == "Toyota"
    assert get_field_value(intake, "vehicles[].annual_km") == 12000


def test_vehicle_fields_respect_explicit_index():
    intake = make_intake()
    assert get_field_value(intake, "vehicles[].make", vehicle_index=1) == "Honda"
    assert get_field_value(intake, "vehicles[].annual_km", vehicle_index=1) == 8000


def test_household_fields_respect_explicit_index():
    intake = make_intake()
    assert get_field_value(intake, "household[].name", household_index=0) == "Household One"
    assert get_field_value(intake, "household[].name", household_index=1) == "Household Two"


def test_count_fields_return_length_not_the_list():
    intake = make_intake()
    assert get_field_value(intake, "insurance_history.accidents_last_6_years") == 1
    assert get_field_value(intake, "insurance_history.convictions_last_3_years") == 2
    assert get_field_value(intake, "insurance_history.cancellations_last_3_years") == 0


def test_unknown_path_raises_attribute_error():
    intake = make_intake()
    with pytest.raises(AttributeError):
        get_field_value(intake, "identity.nonexistent_field")
