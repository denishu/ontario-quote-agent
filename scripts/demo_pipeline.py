"""Demo: run the full plan -> attempt -> dedup pipeline against fake data.

This exercises everything built so far end-to-end without needing a real
source list (registry) or real personal data (uses the checked-in
intake.example.json). It's a hand-run smoke test, not part of the shipped
pipeline or the test suite.

Run:
    python scripts/demo_pipeline.py
"""

from pathlib import Path

from quote_agent.agents import CaptchaDetected, QuoteObtained, StopBeforeSensitiveAction, run_web_attempt
from quote_agent.io import DATA_DIR, load_intake
from quote_agent.models import DistributionType, ProductScope, QuoteStatus, RegistryEntry
from quote_agent.normalize import (
    apply_avoided_underwriter_results,
    apply_result_duplicates,
    find_avoided_underwriter_results,
    find_result_duplicates,
)
from quote_agent.planner import plan_routes

DEMO_EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "evidence" / "demo"

# Fictional example only -- deliberately not read from intake.example.json's
# avoided_underwriters field, since that file is committed to the repo and
# should never encode a real preference (e.g. an applicant's actual family
# insurer). Your real intake.json (gitignored) is where a real value belongs.
DEMO_AVOIDED_UNDERWRITERS = ["Example Mutual Insurance Company"]


def fake_registry() -> list[RegistryEntry]:
    return [
        RegistryEntry(
            registry_id="aviva-direct",
            last_verified_at="2026-08-09T00:00:00Z",
            legal_underwriter="Aviva Insurance Company of Canada",
            insurer_group="Aviva",
            brand_or_program="Aviva Direct",
            distribution_type=DistributionType.DIRECT,
            product_scope=ProductScope.STANDARD_PPA,
            distinct_rate_source_id="aviva-direct",
            quote_url="https://example.com/aviva",
        ),
        RegistryEntry(
            registry_id="mychoice-aggregator",
            last_verified_at="2026-08-09T00:00:00Z",
            legal_underwriter="unknown",
            insurer_group="varies",
            brand_or_program="MyChoice",
            distribution_type=DistributionType.AGGREGATOR,
            product_scope=ProductScope.STANDARD_PPA,
            distinct_rate_source_id="mychoice-aggregator",
            quote_url="https://example.com/mychoice",
        ),
        RegistryEntry(
            registry_id="td-direct",
            last_verified_at="2026-08-09T00:00:00Z",
            legal_underwriter="TD General Insurance Company",
            insurer_group="TD",
            brand_or_program="TD Insurance",
            distribution_type=DistributionType.DIRECT,
            product_scope=ProductScope.STANDARD_PPA,
            distinct_rate_source_id="td-direct",
            quote_url="https://example.com/td",
        ),
        RegistryEntry(
            registry_id="broker-x",
            last_verified_at="2026-08-09T00:00:00Z",
            legal_underwriter="unknown",
            insurer_group="varies",
            brand_or_program="Local Broker X",
            distribution_type=DistributionType.BROKER,
            product_scope=ProductScope.STANDARD_PPA,
            distinct_rate_source_id="broker-x",
            quote_url="https://example.com/brokerx",
        ),
        RegistryEntry(
            registry_id="thinkinsure-broker",
            last_verified_at="2026-08-09T00:00:00Z",
            legal_underwriter="unknown",
            insurer_group="varies",
            brand_or_program="ThinkInsure",
            distribution_type=DistributionType.BROKER,
            product_scope=ProductScope.STANDARD_PPA,
            distinct_rate_source_id="thinkinsure-broker",
            quote_url="https://example.com/thinkinsure",
        ),
    ]


def fake_flows() -> dict:
    """One flow per registry_id above, simulating a range of real outcomes:
    a clean comparable quote, an aggregator that happens to resolve to the
    same underwriter as the direct route (the result-time dedup case), a
    CAPTCHA block, and a sensitive-action stop.
    """

    def aviva_direct(profile):
        return QuoteObtained(
            raw_evidence_text=(
                f"Quote for {profile.identity.legal_name}: "
                "$1,284.00/year, Aviva Insurance Company of Canada"
            ),
            premium_annual=1284.00,
            returned_coverage=profile.coverage_benchmark,
            returned_legal_underwriter="Aviva Insurance Company of Canada",
        )

    def mychoice_aggregator(profile):
        # Deliberately different collision_deductible than the benchmark —
        # proves classify_quote() is doing a real field-by-field diff here,
        # not just echoing a hardcoded "comparable" status. This result
        # also happens to share aviva-direct's underwriter, so it
        # demonstrates two mechanisms in sequence: quoted_non_comparable
        # from the coverage diff, then further reclassified to
        # duplicate_rate_source by the result-time dedup pass below.
        non_comparable_coverage = profile.coverage_benchmark.model_copy(
            update={"collision_deductible": 500}
        )
        return QuoteObtained(
            raw_evidence_text=(
                "MyChoice matched you with Aviva Insurance Company of Canada: "
                "$1,301.50/year, $500 collision deductible"
            ),
            premium_annual=1301.50,
            returned_coverage=non_comparable_coverage,
            returned_legal_underwriter="Aviva Insurance Company of Canada",
        )

    def td_direct(profile):
        raise CaptchaDetected(raw_evidence_text="Please verify you are human before continuing")

    def broker_x(profile):
        raise StopBeforeSensitiveAction(
            raw_evidence_text="Submit Application to receive your bound quote",
            reason="Broker portal required clicking 'Submit Application' to proceed",
        )

    def thinkinsure_broker(profile):
        # ThinkInsure doesn't reveal which carrier it'll return until the
        # quote comes back -- this one happens to resolve to the same
        # underwriter as DEMO_AVOIDED_UNDERWRITERS below. Only the post-hoc
        # avoidance check can catch this; nothing about the registry entry
        # itself signals it in advance. (Fictional example underwriter --
        # this script never reads a real avoided-underwriter value out of
        # intake.example.json, since that file is committed to the repo.)
        return QuoteObtained(
            raw_evidence_text=f"ThinkInsure matched you with {DEMO_AVOIDED_UNDERWRITERS[0]}: $1,190.00/year",
            premium_annual=1190.00,
            returned_coverage=profile.coverage_benchmark,
            returned_legal_underwriter=DEMO_AVOIDED_UNDERWRITERS[0],
        )

    return {
        "aviva-direct": aviva_direct,
        "mychoice-aggregator": mychoice_aggregator,
        "td-direct": td_direct,
        "broker-x": broker_x,
        "thinkinsure-broker": thinkinsure_broker,
    }


def main() -> None:
    intake = load_intake(DATA_DIR / "intake.example.json")
    registry = fake_registry()
    flows = fake_flows()

    plan = plan_routes(intake, registry)
    print("=== Route plan ===")
    print(f"To attempt: {[e.registry_id for e in plan.to_attempt]}")
    for registry_id, reason in plan.excluded.items():
        print(f"  excluded: {registry_id} -- {reason}")

    results = [
        run_web_attempt(entry, intake, flows[entry.registry_id], evidence_dir=DEMO_EVIDENCE_DIR)
        for entry in plan.to_attempt
    ]

    print("\n=== Raw results ===")
    for r in results:
        print(
            f"{r.registry_id:22s} {r.status.value:20s} "
            f"premium={r.premium_annual} underwriter={r.returned_legal_underwriter}"
        )

    dedup_report = find_result_duplicates(results)
    deduped_results = apply_result_duplicates(results, dedup_report)

    avoidance_report = find_avoided_underwriter_results(deduped_results, DEMO_AVOIDED_UNDERWRITERS)
    final_results = apply_avoided_underwriter_results(deduped_results, avoidance_report)

    print("\n=== After result-time dedup + avoided-underwriter check ===")
    for r in final_results:
        print(
            f"{r.registry_id:22s} {r.status.value:20s} "
            f"premium={r.premium_annual} underwriter={r.returned_legal_underwriter}"
        )
        if r.failure_reason:
            print(f"    reason: {r.failure_reason}")

    comparable = [r for r in final_results if r.status is QuoteStatus.QUOTED_COMPARABLE]
    print(f"\n{len(comparable)} comparable quote(s) out of {len(final_results)} attempted market(s).")
    print(f"\nRedacted evidence written to: {DEMO_EVIDENCE_DIR}")


if __name__ == "__main__":
    main()
