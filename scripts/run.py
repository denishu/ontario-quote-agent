"""The real runner: load your real intake + the real registry, decide
which sources are in scope, attempt each one (a dedicated site-specific
flow where one exists, a generic best-effort attempt otherwise), and
write the results back to data/results.json.

This is the one thing that was still missing to go from "all the pieces
work" to "here's a real end-to-end pass over the registry" -- everything
it calls (io, planner, run_web_attempt, the site flows) already existed
and is already tested on its own; this just wires them together in the
order the architecture diagram in the README describes.

Run:
    python scripts/run.py

Requires data/intake.json to exist (gitignored -- copy
data/intake.example.json and fill in your own real information first).
"""

import sys
from pathlib import Path

from quote_agent.agents import make_generic_flow, run_web_attempt, summarize_outcome
from quote_agent.agents.sites.aviva import make_aviva_flow
from quote_agent.agents.sites.onlia import onlia_personal_info_flow
from quote_agent.io import DATA_DIR, load_intake, load_registry, save_results
from quote_agent.models import QuoteStatus
from quote_agent.normalize import (
    apply_avoided_underwriter_results,
    apply_result_duplicates,
    find_avoided_underwriter_results,
    find_result_duplicates,
)
from quote_agent.planner import plan_routes

# One dedicated flow per registry_id that's actually been mapped against
# its real site -- grows over time as more sites get built out like
# onlia.py did. Anything not listed here falls back to a generic
# best-effort attempt (make_generic_flow) rather than being skipped.
# make_aviva_flow() is called here (not passed bare) since it's a
# factory, not a WebFlow itself -- it now obtains its own fresh starting
# URL internally (see aviva.py's _get_fresh_quoter_url), so no argument
# is needed at call time any more than onlia_personal_info_flow needs one.
DEDICATED_FLOWS = {
    "aviva-direct": make_aviva_flow(),
    "onlia-broker": onlia_personal_info_flow,
}


def main() -> None:
    intake_path = DATA_DIR / "intake.json"
    if not intake_path.exists():
        sys.exit(
            f"{intake_path} doesn't exist yet. Copy data/intake.example.json to "
            "data/intake.json and fill in your own real information first."
        )

    intake = load_intake(intake_path)
    registry = load_registry()

    plan = plan_routes(intake, registry)
    print("=== Route plan ===")
    print(f"To attempt: {[e.registry_id for e in plan.to_attempt]}")
    for registry_id, reason in plan.excluded.items():
        print(f"  excluded: {registry_id} -- {reason}")

    results = []
    for entry in plan.to_attempt:
        flow = DEDICATED_FLOWS.get(entry.registry_id) or make_generic_flow(entry)
        print(f"\nAttempting {entry.registry_id} ({'dedicated' if entry.registry_id in DEDICATED_FLOWS else 'generic'} flow)...")
        results.append(run_web_attempt(entry, intake, flow, summarize=summarize_outcome))

    print("\n=== Raw results ===")
    for r in results:
        print(f"{r.registry_id:22s} {r.status.value:20s} premium={r.premium_annual}")

    dedup_report = find_result_duplicates(results)
    deduped_results = apply_result_duplicates(results, dedup_report)

    avoidance_report = find_avoided_underwriter_results(
        deduped_results, intake.consent.avoided_underwriters
    )
    final_results = apply_avoided_underwriter_results(deduped_results, avoidance_report)

    print("\n=== After result-time dedup + avoided-underwriter check ===")
    for r in final_results:
        print(f"{r.registry_id:22s} {r.status.value:20s} premium={r.premium_annual}")
        if r.failure_reason:
            print(f"    reason: {r.failure_reason}")
        if r.evidence.screenshot_ref:
            print(f"    screenshot: {r.evidence.screenshot_ref}")

    comparable = [r for r in final_results if r.status is QuoteStatus.QUOTED_COMPARABLE]
    print(f"\n{len(comparable)} comparable quote(s) out of {len(final_results)} attempted source(s).")

    save_results(final_results)
    print(f"\nResults written to: {DATA_DIR / 'results.json'}")
    print(f"Redacted evidence written to: {Path(__file__).resolve().parents[1] / 'evidence'}")


if __name__ == "__main__":
    main()
