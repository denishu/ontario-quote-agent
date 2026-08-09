from quote_agent.normalize.coverage import classify_quote, diff_coverage
from quote_agent.normalize.dedup import (
    AvoidanceReport,
    DedupReport,
    apply_avoided_underwriter_results,
    apply_result_duplicates,
    distinct_rate_source_count,
    find_avoided_underwriter_results,
    find_result_duplicates,
    group_by_rate_source,
    normalize_underwriter,
)

__all__ = [
    "AvoidanceReport",
    "DedupReport",
    "apply_avoided_underwriter_results",
    "apply_result_duplicates",
    "classify_quote",
    "diff_coverage",
    "distinct_rate_source_count",
    "find_avoided_underwriter_results",
    "find_result_duplicates",
    "group_by_rate_source",
    "normalize_underwriter",
]
