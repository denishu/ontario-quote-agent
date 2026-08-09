from quote_agent.normalize.coverage import classify_quote, diff_coverage
from quote_agent.normalize.dedup import (
    DedupReport,
    apply_result_duplicates,
    distinct_rate_source_count,
    find_result_duplicates,
    group_by_rate_source,
)

__all__ = [
    "DedupReport",
    "apply_result_duplicates",
    "classify_quote",
    "diff_coverage",
    "distinct_rate_source_count",
    "find_result_duplicates",
    "group_by_rate_source",
]
