"""Print plan_routes()'s decision for the full registry against your real
intake -- read-only, no browser, no network call, no write to
data/results.json. Safe to run any number of times, including live on
camera, without touching anything scripts/run_dedicated.py or the
paste-quote flow already put there.

Run:
    python scripts/show_route_plan.py
"""

import sys

from quote_agent.io import DATA_DIR, load_intake, load_registry
from quote_agent.planner import plan_routes


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
    print(f"To attempt ({len(plan.to_attempt)}):")
    for entry in plan.to_attempt:
        print(f"  {entry.registry_id}")
    print(f"\nExcluded ({len(plan.excluded)}):")
    for registry_id, reason in plan.excluded.items():
        print(f"  {registry_id} -- {reason}")


if __name__ == "__main__":
    main()
