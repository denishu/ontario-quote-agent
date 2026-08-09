from quote_agent.models.coverage import CoverageConfig
from quote_agent.models.status import QuoteStatus

# Deliberately excludes optional_benefits and endorsements — those are
# compared separately below because they're keyed/list-shaped, not scalar.
_SCALAR_FIELDS = (
    "effective_date",
    "term_months",
    "third_party_liability_limit",
    "dcpd_included",
    "dcpd_deductible",
    "accident_benefits_mandatory",
    "uninsured_automobile_included",
    "collision_deductible",
    "comprehensive_deductible",
    "all_perils_deductible",
    "telematics_opt_in",
)


def diff_coverage(benchmark: CoverageConfig, returned: CoverageConfig) -> list[str]:
    """Field-by-field diff of a returned quote's coverage against the
    benchmark every source was asked to match. Returns the sorted list of
    field names that differ ("optional_benefits.<name>" for individual
    optional-benefit mismatches). This is deterministic comparison, not an
    LLM judgment call, and it never decides which side is "better" — that's
    for the human comparing results.
    """
    variance: list[str] = []

    for field in _SCALAR_FIELDS:
        if getattr(benchmark, field) != getattr(returned, field):
            variance.append(field)

    benefit_keys = set(benchmark.optional_benefits) | set(returned.optional_benefits)
    for key in benefit_keys:
        if benchmark.optional_benefits.get(key, "unknown") != returned.optional_benefits.get(key, "unknown"):
            variance.append(f"optional_benefits.{key}")

    if set(benchmark.endorsements) != set(returned.endorsements):
        variance.append("endorsements")

    return sorted(variance)


def classify_quote(benchmark: CoverageConfig, returned: CoverageConfig) -> tuple[QuoteStatus, list[str]]:
    """Determine whether a returned quote is exactly comparable to the
    benchmark. An empty diff is quoted_comparable; any variance is
    quoted_non_comparable, with every differing field listed so it can be
    surfaced instead of hidden.
    """
    variance = diff_coverage(benchmark, returned)
    status = QuoteStatus.QUOTED_COMPARABLE if not variance else QuoteStatus.QUOTED_NON_COMPARABLE
    return status, variance
