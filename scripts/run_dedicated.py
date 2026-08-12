"""Re-run just the dedicated site flows (Aviva, Onlia) and merge their
results into the existing data/results.json, rather than run.py's
full-registry sweep -- which overwrites results.json with only whatever
it attempts that run, wiping out anything captured via the paste-quote
flow (MyChoice, belairdirect) in the process.

Skips route planning and result-time dedup/avoided-underwriter
reconciliation entirely: with only two, already-known, unambiguous
dedicated sources in scope, there's nothing for either to meaningfully
resolve, and skipping them keeps this script simple enough to trust for
a one-off refresh before a demo recording.

Run:
    python scripts/run_dedicated.py

Requires data/intake.json to exist (gitignored -- copy
data/intake.example.json and fill in your own real information first).
"""

import sys

from quote_agent.agents import run_web_attempt, summarize_outcome
from quote_agent.agents.sites.aviva import make_aviva_flow
from quote_agent.agents.sites.onlia import onlia_personal_info_flow
from quote_agent.io import DATA_DIR, load_intake, load_registry, load_results, save_results

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
    registry = {e.registry_id: e for e in load_registry()}

    missing = [rid for rid in DEDICATED_FLOWS if rid not in registry]
    if missing:
        sys.exit(f"registry_id(s) not found in data/registry.json: {missing}")

    fresh = []
    for registry_id, flow in DEDICATED_FLOWS.items():
        entry = registry[registry_id]
        print(f"\nAttempting {registry_id}...")
        result = run_web_attempt(entry, intake, flow, summarize=summarize_outcome)
        fresh.append(result)
        print(f"  {result.status.value}  premium={result.premium_annual}")
        if result.failure_reason:
            print(f"  reason: {result.failure_reason}")
        if result.evidence.screenshot_ref:
            print(f"  screenshot: {result.evidence.screenshot_ref}")

    updated_ids = {r.registry_id for r in fresh}
    existing = [r for r in load_results() if r.registry_id not in updated_ids]
    save_results(existing + fresh)
    print(f"\nMerged into: {DATA_DIR / 'results.json'} ({len(existing)} untouched + {len(fresh)} refreshed)")


if __name__ == "__main__":
    main()
