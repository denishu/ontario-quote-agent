from collections import defaultdict

from quote_agent.models import RegistryEntry


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
