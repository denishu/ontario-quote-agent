from datetime import datetime, timezone
from pathlib import Path

from quote_agent.evidence.redact import redact_text
from quote_agent.models import IntakeProfile

EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "evidence"


def save_evidence(
    registry_id: str,
    raw_text: str,
    intake: IntakeProfile,
    suffix: str = "txt",
    evidence_dir: Path | None = None,
) -> str:
    """Redact raw_text against known intake values and save it under
    evidence/. Returns the artifact_ref to store on Evidence.artifact_ref.

    raw_text should be the relevant snippet (the quote/result region, a
    CAPTCHA notice, a call summary) — not a full-page capture, to keep
    both storage and any later LLM parsing cheap. Filenames use a
    colon-free timestamp so this works on Windows.
    """
    directory = evidence_dir or EVIDENCE_DIR
    directory.mkdir(parents=True, exist_ok=True)

    redacted = redact_text(raw_text, intake)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{registry_id}-{timestamp}.{suffix}"
    (directory / filename).write_text(redacted, encoding="utf-8")

    return f"evidence/{filename}"
