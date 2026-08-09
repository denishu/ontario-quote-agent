from pathlib import Path

from quote_agent.evidence import save_evidence
from quote_agent.models import (
    Address,
    Consent,
    ConsentMode,
    CoverageConfig,
    Identity,
    InsuranceHistory,
    IntakeProfile,
)


def make_intake() -> IntakeProfile:
    return IntakeProfile(
        consent=Consent(timestamp="2026-08-09T09:00:00Z", mode=ConsentMode.LIVE_QUOTE),
        identity=Identity(legal_name="Jane Q. Applicant", date_of_birth="1990-05-15"),
        contact_email="jane@example.com",
        contact_phone="416-555-1234",
        address=Address(street="123 Main St", city="Toronto", postal_code="M5V 3A8"),
        vehicles=[],
        insurance_history=InsuranceHistory(),
        coverage_benchmark=CoverageConfig(
            effective_date="2026-09-01", third_party_liability_limit=2_000_000, dcpd_included=True
        ),
    )


def test_save_evidence_writes_redacted_file(tmp_path: Path):
    intake = make_intake()
    raw_text = "Quote for Jane Q. Applicant: annual premium $1,234.56"

    artifact_ref = save_evidence("test-registry-id", raw_text, intake, evidence_dir=tmp_path)

    filename = artifact_ref.removeprefix("evidence/")
    saved_path = tmp_path / filename
    assert saved_path.exists()

    content = saved_path.read_text(encoding="utf-8")
    assert "Jane Q. Applicant" not in content
    assert "[REDACTED:legal_name]" in content
    assert "$1,234.56" in content


def test_save_evidence_filename_includes_registry_id_and_has_no_colons(tmp_path: Path):
    intake = make_intake()
    artifact_ref = save_evidence("aviva-direct", "some text", intake, evidence_dir=tmp_path)
    assert artifact_ref.startswith("evidence/aviva-direct-")
    assert ":" not in artifact_ref
