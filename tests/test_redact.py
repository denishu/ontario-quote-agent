from quote_agent.models import (
    Address,
    Consent,
    ConsentMode,
    CoverageConfig,
    HouseholdMember,
    Identity,
    InsuranceHistory,
    IntakeProfile,
    Vehicle,
)
from quote_agent.evidence import redact_text


def make_intake() -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(
            legal_name="Jane Q. Applicant",
            date_of_birth="1990-05-15",
            licence_number="A1234-56789-01234",
        ),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        address=Address(street="123 Main St", unit="4B", city="Toronto", postal_code="M5V 3A8"),
        household=[HouseholdMember(name="John Applicant", relationship="parent", licensed=True)],
        vehicles=[
            Vehicle(
                vin="1HGCM82633A123456",
                model_year=2020,
                make="Toyota",
                model="Corolla",
                ownership="owned",
                primary_use="commute",
                annual_km=12000,
            )
        ],
        insurance_history=InsuranceHistory(),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01", third_party_liability_limit=2_000_000, dcpd_included=True
        ),
    )


def test_exact_name_match_is_redacted():
    intake = make_intake()
    text = "Quote prepared for Jane Q. Applicant, annual premium $1,234.56"
    redacted = redact_text(text, intake)
    assert "Jane Q. Applicant" not in redacted
    assert "[REDACTED:legal_name]" in redacted
    assert "$1,234.56" in redacted


def test_case_insensitive_match_is_redacted():
    intake = make_intake()
    text = "APPLICANT NAME: JANE Q. APPLICANT"
    redacted = redact_text(text, intake)
    assert "JANE Q. APPLICANT" not in redacted
    assert "[REDACTED:legal_name]" in redacted


def test_phone_number_without_dashes_is_redacted():
    intake = make_intake()
    text = "Callback number on file: 4165551234"
    redacted = redact_text(text, intake)
    assert "4165551234" not in redacted
    assert "[REDACTED:contact_phone]" in redacted


def test_postal_code_without_space_is_redacted():
    intake = make_intake()
    text = "Garaging postal code M5V3A8 confirmed"
    redacted = redact_text(text, intake)
    assert "M5V3A8" not in redacted
    assert "[REDACTED:postal_code]" in redacted


def test_vin_is_redacted():
    intake = make_intake()
    text = "Vehicle on file: VIN 1HGCM82633A123456"
    redacted = redact_text(text, intake)
    assert "1HGCM82633A123456" not in redacted
    assert "[REDACTED:vehicle_0_vin]" in redacted


def test_household_member_name_is_redacted():
    intake = make_intake()
    text = "Secondary driver: John Applicant"
    redacted = redact_text(text, intake)
    assert "John Applicant" not in redacted
    assert "[REDACTED:household_0_name]" in redacted


def test_licence_number_and_compact_variant_are_redacted():
    intake = make_intake()
    text_with_dashes = "Licence on file: A1234-56789-01234"
    text_compact = "Licence on file: A12345678901234"
    assert "[REDACTED:licence_number]" in redact_text(text_with_dashes, intake)
    assert "[REDACTED:licence_number]" in redact_text(text_compact, intake)


def test_unrelated_text_is_left_untouched():
    intake = make_intake()
    text = "Your annual premium is $1,234.56 with a $1,000 collision deductible."
    assert redact_text(text, intake) == text
