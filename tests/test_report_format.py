from quote_agent.agents.flow import FlowResult, StepResult
from quote_agent.agents.loop import FillReport
from quote_agent.agents.report_format import format_fill_report, format_flow_result
from quote_agent.models import (
    Address,
    Consent,
    ConsentMode,
    CoverageConfig,
    Identity,
    InsuranceHistory,
    IntakeProfile,
    Vehicle,
)


def make_intake() -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(
            legal_name="Jane Applicant", date_of_birth="1990-01-01", licence_number="A1234-56789-01234"
        ),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        address=Address(street="123 Main St", city="Toronto", province="Ontario", postal_code="M5V 3A8"),
        vehicles=[
            Vehicle(
                vin="1REALVIN000000001",
                model_year=2020,
                make="Toyota",
                model="Corolla",
                ownership="owned",
                primary_use="commute",
                annual_km=12000,
                winter_tires=True,
            )
        ],
        insurance_history=InsuranceHistory(),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01", third_party_liability_limit=2_000_000, dcpd_included=True
        ),
    )


def test_format_fill_report_redacts_sensitive_fields_by_path():
    # "Jane" (the isolated first name) is deliberately not a substring of
    # anything the existing evidence redactor would necessarily catch if
    # checked the other way around (redact_text looks for whether a known
    # full value like "Jane Applicant" appears *within* the text being
    # checked, not whether a short value like "Jane" appears within it) --
    # redaction here is unconditional by field path instead, so it can't
    # be fooled by an isolated value that a substring check would miss.
    report = FillReport(
        filled={
            "First Name": "identity.first_name",
            "Last Name": "identity.last_name",
            "Date of birth": "identity.date_of_birth",
            "Licence number": "identity.licence_number",
            "Street address": "address.street",
            "City": "address.city",
            "Vehicle use": "vehicles[].primary_use",
            "Winter tires": "vehicles[].winter_tires",
        }
    )
    output = format_fill_report(report, make_intake())

    assert "Jane" not in output
    assert "Applicant" not in output
    assert "1990-01-01" not in output
    assert "A1234-56789-01234" not in output
    assert "123 Main St" not in output
    assert "Toronto" not in output

    assert output.count("[REDACTED]") == 6  # every sensitive field above, exactly

    # non-sensitive fields still show their real value -- redaction isn't blanket
    assert "'commute'" in output
    assert "True" in output


def test_format_fill_report_shows_unresolved_skipped_and_failed_sections():
    report = FillReport(
        unresolved=["Some novel question"],
        skipped_unknown_widget=["A stepper widget"],
        failed_to_fill={"A broken field": "TimeoutError: something went wrong"},
    )
    output = format_fill_report(report, make_intake())

    assert "'Some novel question'" in output
    assert "'A stepper widget'" in output
    assert "'A broken field'" in output
    assert "TimeoutError: something went wrong" in output


def test_format_flow_result_numbers_and_separates_each_step():
    report1 = FillReport(filled={"Vehicle use": "vehicles[].primary_use"})
    report2 = FillReport(unresolved=["Something on page 2"])
    result = FlowResult(
        steps=[
            StepResult(fill_report=report1, advanced=True, changed=True),
            StepResult(fill_report=report2, advanced=False, changed=False),
        ]
    )
    output = format_flow_result(result, make_intake())

    assert "=== step 1  (advanced=True, changed=True) ===" in output
    assert "=== step 2  (advanced=False, changed=False) ===" in output
    assert output.index("step 1") < output.index("step 2")
