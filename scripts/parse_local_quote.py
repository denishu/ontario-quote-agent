"""Parse a manually-saved quote-result page into a real ResultEntry --
decouples the "AI compares quotes" story from live-run risk, for a
source whose quote lands as an on-page result rather than a downloadable
artifact (confirmed on a real site, belairdirect: price plus a coverage
breakdown, no PDF).

Save the quote result page locally first (in your browser: Ctrl+S / File
> Save Page As...) -- this script never fetches anything live itself,
only reads the file you already saved.

Feeds through the exact same build_result()/classify_quote() pipeline a
live automated result would: real evidence saved (redacted), real
deterministic coverage diff against your benchmark, a real
quoted_comparable/quoted_non_comparable status -- not a special case.

Run:
    python scripts/parse_local_quote.py <path-to-saved.html> <registry_id>

Example:
    python scripts/parse_local_quote.py evidence/manual/belairdirect.html belairdirect-direct

Requires data/intake.json to exist (gitignored -- copy
data/intake.example.json and fill in your own real information first).
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from quote_agent.agents import build_result, extract_quote_from_text
from quote_agent.io import DATA_DIR, load_intake, load_registry, load_results, save_results


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python scripts/parse_local_quote.py <path-to-saved.html> <registry_id>")

    html_path = Path(sys.argv[1])
    registry_id = sys.argv[2]

    if not html_path.exists():
        sys.exit(f"{html_path} doesn't exist.")

    intake_path = DATA_DIR / "intake.json"
    if not intake_path.exists():
        sys.exit(
            f"{intake_path} doesn't exist yet. Copy data/intake.example.json to "
            "data/intake.json and fill in your own real information first."
        )
    intake = load_intake(intake_path)

    registry = load_registry()
    entry = next((e for e in registry if e.registry_id == registry_id), None)
    if entry is None:
        sys.exit(f"No registry entry with registry_id={registry_id!r} in data/registry.json.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri())
        page_text = page.inner_text("body")
        browser.close()

    print(f"Extracting quote details for {registry_id} from {html_path}...")
    outcome = extract_quote_from_text(page_text, intake.coverage_benchmark)
    result = build_result(entry, intake, outcome)

    print(
        f"\n{result.registry_id:22s} {result.status.value:20s} "
        f"premium={result.premium_annual} underwriter={result.returned_legal_underwriter}"
    )
    if result.coverage_variance:
        print(f"    differs from benchmark: {', '.join(result.coverage_variance)}")

    # Replace only this registry_id's entry -- everything else already in
    # results.json (a real automated attempt, or an earlier parsed page)
    # stays untouched.
    existing = [r for r in load_results() if r.registry_id != registry_id]
    save_results(existing + [result])
    print(f"\nSaved to {DATA_DIR / 'results.json'} (replacing any prior result for {registry_id!r}).")


if __name__ == "__main__":
    main()
