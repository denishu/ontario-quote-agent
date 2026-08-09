from collections import defaultdict
from dataclasses import dataclass, field

from quote_agent.models import RegistryEntry, ResultEntry
from quote_agent.models.status import QuoteStatus


def group_by_rate_source(entries: list[RegistryEntry]) -> dict[str, list[RegistryEntry]]:
    """Group registry entries by distinct_rate_source_id.

    A consumer brand, legal underwriter and broker panel can all describe
    the same underlying rate source (e.g. a direct brand and a broker panel
    both ultimately place business with the same underwriter). This is the
    single place that collapses those relationships so nothing gets
    attempted or counted as a distinct market twice.
    """
    groups: dict[str, list[RegistryEntry]] = defaultdict(list)
    for entry in entries:
        groups[entry.distinct_rate_source_id].append(entry)
    return dict(groups)


def distinct_rate_source_count(entries: list[RegistryEntry]) -> int:
    return len(group_by_rate_source(entries))


def normalize_underwriter(name: str) -> str:
    """Plain, deterministic normalization only — case and whitespace, no
    abbreviation expansion or fuzzy matching. Two names that differ by more
    than that (e.g. "Co." vs "Company") won't be caught here; see the
    submission's known-limitations note.
    """
    return " ".join(name.split()).strip(" .").casefold()


@dataclass
class DedupReport:
    """Maps a later result's registry_id to a human-readable reason naming
    the earlier (primary) registry_id it shares a returned_legal_underwriter
    with. Produced by find_result_duplicates(); nothing is mutated until
    apply_result_duplicates() is called with it.
    """

    duplicates: dict[str, str] = field(default_factory=dict)


def find_result_duplicates(results: list[ResultEntry]) -> DedupReport:
    """Group results by the legal underwriter actually returned during
    execution — not the registry's a-priori assumption — and flag every
    result after the first in each group.

    This is the only reliable way to catch a broker or aggregator resolving
    to the same underlying carrier as an already-attempted direct route:
    that relationship generally isn't knowable until after both attempts
    return a result. Exact match only (after normalization) — deliberately
    not an LLM judgment call, since insurer groups can contain several
    genuinely distinct legal underwriters (e.g. Aviva's group has five) and
    a name-similarity heuristic risks merging two of them incorrectly.
    """
    seen: dict[str, str] = {}  # normalized underwriter -> primary registry_id
    duplicates: dict[str, str] = {}

    for result in results:
        if not result.returned_legal_underwriter:
            continue
        key = normalize_underwriter(result.returned_legal_underwriter)
        primary_id = seen.get(key)
        if primary_id is not None:
            duplicates[result.registry_id] = (
                f"duplicate_rate_source of '{primary_id}' "
                f"(both returned legal_underwriter='{result.returned_legal_underwriter}')"
            )
        else:
            seen[key] = result.registry_id

    return DedupReport(duplicates=duplicates)


def apply_result_duplicates(results: list[ResultEntry], report: DedupReport) -> list[ResultEntry]:
    """Return a new list where every flagged result has its status
    overwritten to duplicate_rate_source. The original premium and coverage
    are preserved (not deleted) so the evidence trail stays intact — the
    spec requires a failed or superseded attempt never simply disappear.
    """
    updated: list[ResultEntry] = []
    for result in results:
        reason = report.duplicates.get(result.registry_id)
        if reason is None:
            updated.append(result)
            continue
        updated.append(
            ResultEntry.model_validate(
                result.model_dump()
                | {
                    "status": QuoteStatus.DUPLICATE_RATE_SOURCE.value,
                    "failure_reason": reason,
                    "next_action": "Compare against the primary result instead; this route is not a distinct market.",
                }
            )
        )
    return updated


@dataclass
class AvoidanceReport:
    """Maps a registry_id whose returned_legal_underwriter matched
    consent.avoided_underwriters to a human-readable reason. Produced by
    find_avoided_underwriter_results(); nothing is mutated until
    apply_avoided_underwriter_results() is called with it.
    """

    avoided: dict[str, str] = field(default_factory=dict)


def find_avoided_underwriter_results(
    results: list[ResultEntry], avoided_underwriters: list[str]
) -> AvoidanceReport:
    """Flag any result whose returned_legal_underwriter matches an entry in
    consent.avoided_underwriters — e.g. an insurer the applicant is already
    covered through via a family policy.

    This exists because avoiding a *registry entry* (via
    excluded_source_ids) only protects against the direct route. A broker
    or aggregator can still resolve to the same avoided underwriter, and
    that's only knowable after a result comes back — the same reason
    find_result_duplicates() has to run post-hoc rather than at planning
    time. Same normalization, same exact-match-only reasoning: an insurer
    group can contain several distinct legal underwriters, so this must
    never fuzzy-match on brand or group name.
    """
    normalized_avoid_list = {
        normalize_underwriter(name): name for name in avoided_underwriters if name
    }
    avoided: dict[str, str] = {}

    for result in results:
        if not result.returned_legal_underwriter:
            continue
        key = normalize_underwriter(result.returned_legal_underwriter)
        if key in normalized_avoid_list:
            avoided[result.registry_id] = (
                f"legal_underwriter '{result.returned_legal_underwriter}' matches "
                f"consent.avoided_underwriters entry '{normalized_avoid_list[key]}' -- "
                "excluded per applicant preference, not an insurer eligibility rule"
            )

    return AvoidanceReport(avoided=avoided)


def apply_avoided_underwriter_results(
    results: list[ResultEntry], report: AvoidanceReport
) -> list[ResultEntry]:
    """Return a new list where every flagged result has its status
    overwritten to ineligible. The enum has no status specifically for "the
    applicant chose to avoid this insurer" — ineligible is the closest fit
    among the fixed set, so the real reason is always spelled out in
    failure_reason rather than left to the status alone. Premium and
    coverage are preserved, not deleted.
    """
    updated: list[ResultEntry] = []
    for result in results:
        reason = report.avoided.get(result.registry_id)
        if reason is None:
            updated.append(result)
            continue
        updated.append(
            ResultEntry.model_validate(
                result.model_dump()
                | {
                    "status": QuoteStatus.INELIGIBLE.value,
                    "failure_reason": reason,
                    "next_action": "Do not pursue -- applicant is already covered through this underwriter.",
                }
            )
        )
    return updated
