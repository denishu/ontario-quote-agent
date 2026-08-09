import re

from quote_agent.models import IntakeProfile


def sensitive_values(intake: IntakeProfile) -> dict[str, str]:
    """Map a label to a known sensitive value pulled from the intake
    profile. This is the redaction list — everything on it gets stripped
    out of captured evidence, rather than trying to detect PII
    heuristically. We can afford to be exact here because we already know
    precisely what we submitted; it came from this same file.
    """
    values: dict[str, str] = {
        "legal_name": intake.identity.legal_name,
        "date_of_birth": intake.identity.date_of_birth,
        "contact_email": intake.contact_email,
        "contact_phone": intake.contact_phone,
        "street": intake.address.street,
        "postal_code": intake.address.postal_code,
    }
    if intake.identity.licence_number:
        values["licence_number"] = intake.identity.licence_number
    if intake.address.unit:
        values["address_unit"] = intake.address.unit
    for i, vehicle in enumerate(intake.vehicles):
        values[f"vehicle_{i}_vin"] = vehicle.vin
    for i, member in enumerate(intake.household):
        values[f"household_{i}_name"] = member.name

    return {label: value for label, value in values.items() if value}


def _variants(value: str) -> list[str]:
    """A handful of plausible reformattings a site might display a value
    in (e.g. a licence number or postal code with/without a separator).
    Not exhaustive — see the known-limitations note on formatting variants
    the redactor can't anticipate. Longest first so a longer variant isn't
    left partially matched after a shorter one is replaced.
    """
    stripped = value.strip()
    variants = {
        stripped,
        stripped.replace(" ", ""),
        stripped.replace("-", ""),
        stripped.replace(" ", "").replace("-", ""),
    }
    return sorted((v for v in variants if v), key=len, reverse=True)


def redact_text(text: str, intake: IntakeProfile) -> str:
    """Replace every occurrence of a known sensitive value from `intake`
    with a labelled placeholder. Deterministic substring matching against
    values we already know we submitted — never PII pattern-guessing.
    """
    redacted = text
    for label, value in sensitive_values(intake).items():
        for variant in _variants(value):
            redacted = re.sub(re.escape(variant), f"[REDACTED:{label}]", redacted, flags=re.IGNORECASE)
    return redacted
