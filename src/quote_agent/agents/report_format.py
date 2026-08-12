"""Human-readable rendering of FillReport/FlowResult -- built specifically
to be safe to paste anywhere, including back into a chat with an LLM.

FillReport itself only ever carries label -> field path, deliberately
never a value (see loop.py) -- but seeing the actual answer that went
into a field matters for real debugging, so this recomputes each value
fresh from intake purely for display, and redacts it first if it comes
from a known-sensitive field path. Redaction here is by field *path*,
not by pattern-matching the value against known sensitive strings (the
way evidence.redact.redact_text works) -- a value like a first name
alone ("John") isn't a substring of the stored full name ("John Smith"),
so pattern-matching would silently miss exactly the values most likely
to appear alone in a fill report. Redacting by path is unconditional and
doesn't depend on the value happening to match anything.
"""

from quote_agent.agents.flow import FlowResult
from quote_agent.agents.loop import FillReport
from quote_agent.mapping import get_field_value
from quote_agent.models import IntakeProfile

_SENSITIVE_PATH_PREFIXES = (
    "identity.legal_name",
    "identity.first_name",
    "identity.last_name",
    "identity.date_of_birth",
    "identity.licence_number",
    "address.",  # street/unit/postal_code/city -- redact the whole block, not just some of it
    "contact_email",
    "contact_phone",
    "vehicles[].vin",
    "household[].name",
)


def _is_sensitive_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in _SENSITIVE_PATH_PREFIXES)


def format_fill_report(
    report: FillReport,
    intake: IntakeProfile,
    *,
    vehicle_index: int = 0,
    household_index: int = 0,
) -> str:
    """Render one FillReport as clean, aligned text: every filled field's
    label, resolved path, and the actual value used (redacted if the path
    is sensitive), plus unresolved/unknown-widget/failed labels.
    """
    lines: list[str] = []

    lines.append(f"FILLED ({len(report.filled)})")
    for label, path in sorted(report.filled.items()):
        if _is_sensitive_path(path):
            display_value = "[REDACTED]"
        else:
            value = get_field_value(intake, path, vehicle_index=vehicle_index, household_index=household_index)
            display_value = repr(value)
        lines.append(f"  {label!r}")
        lines.append(f"      -> {path} = {display_value}")

    lines.append(f"\nUNRESOLVED ({len(report.unresolved)})")
    for label in sorted(report.unresolved):
        lines.append(f"  {label!r}")

    lines.append(f"\nSKIPPED - UNKNOWN WIDGET ({len(report.skipped_unknown_widget)})")
    for label in sorted(report.skipped_unknown_widget):
        lines.append(f"  {label!r}")

    lines.append(f"\nFAILED TO FILL ({len(report.failed_to_fill)})")
    for label, error in sorted(report.failed_to_fill.items()):
        lines.append(f"  {label!r}")
        lines.append(f"      {error}")

    return "\n".join(lines)


def format_flow_result(
    result: FlowResult,
    intake: IntakeProfile,
    *,
    vehicle_index: int = 0,
    household_index: int = 0,
) -> str:
    """Render every step of a FlowResult (from run_flow_steps) as one
    readable block, each step separated and numbered.
    """
    sections = []
    for i, step in enumerate(result.steps, start=1):
        body = format_fill_report(
            step.fill_report, intake, vehicle_index=vehicle_index, household_index=household_index
        )
        sections.append(
            f"=== step {i}  (advanced={step.advanced}, changed={step.changed}) ===\n{body}"
        )
    return "\n\n".join(sections)
