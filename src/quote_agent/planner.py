from dataclasses import dataclass, field

from quote_agent.models import IntakeProfile, RegistryEntry
from quote_agent.normalize import group_by_rate_source


@dataclass
class RoutePlan:
    """Output of plan_routes(): which registry entries to actually attempt
    this run, and why every other entry was left out. Nothing here talks to
    a browser or a phone line — this is planning, not execution.
    """

    to_attempt: list[RegistryEntry]
    excluded: dict[str, str] = field(default_factory=dict)  # registry_id -> reason


def plan_routes(intake: IntakeProfile, registry: list[RegistryEntry]) -> RoutePlan:
    """Decide which registry entries are in scope for this run.

    Applies consent first — excluded_source_ids always wins, then a
    non-empty approved_source_ids allowlist, then permitted_channels — and
    only then collapses entries that share a distinct_rate_source_id, so a
    brand and the broker panel that resolves to the same underlying carrier
    aren't both attempted.
    """
    consent = intake.consent
    excluded: dict[str, str] = {}
    candidates: list[RegistryEntry] = []

    for entry in registry:
        if entry.registry_id in consent.excluded_source_ids:
            excluded[entry.registry_id] = "excluded by consent.excluded_source_ids"
        elif consent.approved_source_ids and entry.registry_id not in consent.approved_source_ids:
            excluded[entry.registry_id] = "not in consent.approved_source_ids"
        elif consent.permitted_channels and entry.distribution_type not in consent.permitted_channels:
            excluded[entry.registry_id] = (
                f"distribution_type '{entry.distribution_type.value}' not in consent.permitted_channels"
            )
        else:
            candidates.append(entry)

    to_attempt: list[RegistryEntry] = []
    for rate_source_id, entries in group_by_rate_source(candidates).items():
        chosen, *duplicates = entries
        to_attempt.append(chosen)
        for dup in duplicates:
            excluded[dup.registry_id] = (
                f"duplicate_rate_source of '{chosen.registry_id}' "
                f"(distinct_rate_source_id={rate_source_id})"
            )

    return RoutePlan(to_attempt=to_attempt, excluded=excluded)
