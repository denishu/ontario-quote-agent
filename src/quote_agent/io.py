"""Load and save the three data files against their Pydantic schemas.

Centralized here so every caller gets the same validation instead of raw
json.load/dump scattered around the codebase.
"""

from pathlib import Path

from pydantic import TypeAdapter

from quote_agent.models import IntakeProfile, RegistryEntry, ResultEntry

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

_registry_adapter = TypeAdapter(list[RegistryEntry])
_results_adapter = TypeAdapter(list[ResultEntry])


def load_intake(path: Path | None = None) -> IntakeProfile:
    path = path or DATA_DIR / "intake.json"
    return IntakeProfile.model_validate_json(path.read_text(encoding="utf-8"))


def load_registry(path: Path | None = None) -> list[RegistryEntry]:
    path = path or DATA_DIR / "registry.json"
    return _registry_adapter.validate_json(path.read_text(encoding="utf-8"))


def save_registry(entries: list[RegistryEntry], path: Path | None = None) -> None:
    path = path or DATA_DIR / "registry.json"
    path.write_text(_registry_adapter.dump_json(entries, indent=2).decode("utf-8"), encoding="utf-8")


def load_results(path: Path | None = None) -> list[ResultEntry]:
    path = path or DATA_DIR / "results.json"
    return _results_adapter.validate_json(path.read_text(encoding="utf-8"))


def save_results(entries: list[ResultEntry], path: Path | None = None) -> None:
    path = path or DATA_DIR / "results.json"
    path.write_text(_results_adapter.dump_json(entries, indent=2).decode("utf-8"), encoding="utf-8")
