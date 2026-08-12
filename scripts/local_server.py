"""Local dev server: serves the static web/ files (same as `python -m
http.server`) plus two JSON API endpoints:

  POST   /api/parse-quote        -- extract + compare a pasted quote page
  DELETE /api/results/<id>       -- one-click delete, per the challenge
                                     brief's own requirement ("a one-click
                                     delete function... delete hackathon
                                     quote data after judging unless the
                                     participant explicitly chooses
                                     otherwise"). Removes the result from
                                     data/results.json and its evidence
                                     file(s) -- a real delete, not just
                                     hiding the card.

So web/paste-quote.html and the delete button on each QuoteON card can
run the real pipeline without an Anthropic API key ever touching browser
code.

Deliberately built on the standard library's http.server rather than a
new framework dependency (Flask, FastAPI, etc.) -- this project's own
dependency list stays exactly pydantic/playwright/anthropic/dotenv, and
the one endpoint this needs is simple enough not to need one.

Reuses the same extraction + registry-matching logic as
parse_local_quotes.py (see that script's docstring for the underlying
design decisions) -- this is the same pipeline, just reachable from a
paste box instead of a saved file on disk.

Run:
    python scripts/local_server.py [port]

Defaults to port 8123 -- the same port the static-only `python -m
http.server` workflow has been using; this replaces that command, since
it serves the exact same static files plus the new API route. Requires
data/intake.json to exist (gitignored -- copy data/intake.example.json
and fill in your own real information first).
"""

import json
import sys
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from quote_agent.agents import build_result, extract_quotes_from_text  # noqa: E402
from quote_agent.io import DATA_DIR, load_intake, load_registry, load_results, save_results  # noqa: E402
from quote_agent.models import RegistryEntry  # noqa: E402


def _find_registry_entry(underwriter: str, registry: list[RegistryEntry]) -> RegistryEntry | None:
    normalized = underwriter.strip().casefold()
    for entry in registry:
        known = entry.legal_underwriter.strip().casefold()
        if normalized in known or known in normalized:
            return entry
    return None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def do_POST(self):
        if self.path != "/api/parse-quote":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Malformed JSON body"})
            return

        page_text = (body.get("text") or "").strip()
        if not page_text:
            self._send_json(400, {"error": "No text provided"})
            return

        intake_path = DATA_DIR / "intake.json"
        if not intake_path.exists():
            self._send_json(
                400,
                {
                    "error": (
                        "data/intake.json doesn't exist -- copy data/intake.example.json "
                        "and fill in your own real information first"
                    )
                },
            )
            return

        try:
            intake = load_intake(intake_path)
            registry = load_registry()
            outcomes = extract_quotes_from_text(page_text, intake.coverage_benchmark)
        except Exception as exc:  # deliberate catch-all: a bad paste or API hiccup must not crash the server
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return

        saved = []
        skipped = []
        for outcome in outcomes:
            entry = _find_registry_entry(outcome.returned_legal_underwriter, registry)
            if entry is None:
                skipped.append(outcome.returned_legal_underwriter)
                continue
            saved.append(build_result(entry, intake, outcome))

        if saved:
            updated_ids = {r.registry_id for r in saved}
            existing = [r for r in load_results() if r.registry_id not in updated_ids]
            save_results(existing + saved)

        self._send_json(
            200,
            {
                "saved": [
                    {
                        "registry_id": r.registry_id,
                        "status": r.status.value,
                        "premium_annual": r.premium_annual,
                        "underwriter": r.returned_legal_underwriter,
                        "confidence": r.confidence.value,
                        "coverage_variance": r.coverage_variance,
                    }
                    for r in saved
                ],
                "skipped": skipped,
            },
        )

    def do_DELETE(self):
        prefix = "/api/results/"
        if not self.path.startswith(prefix):
            self.send_error(404)
            return

        registry_id = unquote(self.path[len(prefix):])
        results = load_results()
        matching = [r for r in results if r.registry_id == registry_id]
        remaining = [r for r in results if r.registry_id != registry_id]

        if not matching:
            self._send_json(404, {"error": f"No result found for registry_id={registry_id!r}"})
            return

        save_results(remaining)

        # A real delete, not just hiding the card -- also removes the
        # evidence file(s) this result pointed at, so nothing sensitive
        # keeps sitting on disk once its result is gone. Tolerant of a
        # file that's already missing (e.g. deleted by hand already).
        evidence_removed = []
        for result in matching:
            for ref in (result.evidence.artifact_ref, result.evidence.screenshot_ref):
                if not ref:
                    continue
                path = REPO_ROOT / ref
                if path.exists():
                    path.unlink()
                    evidence_removed.append(ref)

        self._send_json(200, {"deleted": registry_id, "evidence_removed": evidence_removed})

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[server] {self.address_string()} - {format % args}")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    TCPServer.allow_reuse_address = True
    with TCPServer(("", port), Handler) as httpd:
        print(f"Serving {REPO_ROOT} at http://localhost:{port}")
        print(f"QuoteON dashboard:  http://localhost:{port}/web/index.html")
        print(f"Paste a quote:      http://localhost:{port}/web/paste-quote.html")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
