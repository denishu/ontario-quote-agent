"""Parse a saved aggregator/comparison results page -- several
underwriters' quotes shown at once -- into real ResultEntry rows. See
parse_local_quote.py for the single-quote version (belairdirect-style:
one page, one quote, full coverage breakdown).

Save the page's visible text locally first (select all on the page,
copy, paste into a plain .txt file) -- more reliable than "Save Page
As" for a JavaScript-rendered page: confirmed live on a real site
(MyChoice) that its saved HTML has a completely empty body, because
Chrome renames the page's own JS bundle to *.download when saving a
"complete webpage" so it never executes on reopen, and the page never
re-renders as a result.

Matches each extracted quote to a registry entry by underwriter name
(substring match against legal_underwriter) -- prints a warning and
skips any quote with no matching entry, rather than silently inventing
one. A genuinely new underwriter surfaced by an aggregator needs a real
registry.json entry added by hand first (see wawanesa-via-mychoice etc.
for the pattern this project already uses).

Run:
    python scripts/parse_local_quotes.py <path-to-saved.txt>

Requires data/intake.json to exist (gitignored -- copy
data/intake.example.json and fill in your own real information first).
"""

import sys
from pathlib import Path

from quote_agent.agents import build_result, extract_quotes_from_text
from quote_agent.io import DATA_DIR, load_intake, load_registry, load_results, save_results
from quote_agent.models import RegistryEntry


def _find_registry_entry(underwriter: str, registry: list[RegistryEntry]) -> RegistryEntry | None:
    normalized = underwriter.strip().casefold()
    for entry in registry:
        known = entry.legal_underwriter.strip().casefold()
        if normalized in known or known in normalized:
            return entry
    return None


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/parse_local_quotes.py <path-to-saved.txt>")

    text_path = Path(sys.argv[1])
    if not text_path.exists():
        sys.exit(f"{text_path} doesn't exist.")

    intake_path = DATA_DIR / "intake.json"
    if not intake_path.exists():
        sys.exit(
            f"{intake_path} doesn't exist yet. Copy data/intake.example.json to "
            "data/intake.json and fill in your own real information first."
        )
    intake = load_intake(intake_path)
    registry = load_registry()

    page_text = text_path.read_text(encoding="utf-8")
    print(f"Extracting quotes from {text_path}...")
    outcomes = extract_quotes_from_text(page_text, intake.coverage_benchmark)

    new_results = []
    for outcome in outcomes:
        entry = _find_registry_entry(outcome.returned_legal_underwriter, registry)
        if entry is None:
            print(
                f"  SKIPPED: no registry entry matches underwriter "
                f"{outcome.returned_legal_underwriter!r} -- add one to data/registry.json first"
            )
            continue
        result = build_result(entry, intake, outcome)
        new_results.append(result)
        print(
            f"  {result.registry_id:26s} {result.status.value:20s} "
            f"premium={result.premium_annual} underwriter={result.returned_legal_underwriter} "
            f"confidence={result.confidence.value}"
        )
        if result.coverage_variance:
            print(f"      differs from benchmark: {', '.join(result.coverage_variance)}")

    if not new_results:
        print("\nNo results extracted -- nothing saved.")
        return

    # Replace only the registry_ids just extracted -- everything else
    # already in results.json (a real automated attempt, or an earlier
    # parsed page) stays untouched.
    updated_ids = {r.registry_id for r in new_results}
    existing = [r for r in load_results() if r.registry_id not in updated_ids]
    save_results(existing + new_results)
    print(f"\nSaved {len(new_results)} result(s) to {DATA_DIR / 'results.json'}.")


if __name__ == "__main__":
    main()
