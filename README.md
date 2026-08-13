# ontario-quote-agent

Personal-use agent that takes one real Ontario auto-insurance profile and attempts to obtain
comparable quotes from distinct rate sources across direct, broker, aggregator, mutual and
residual-market channels. Every attempt ends in a normalized, evidence-backed result — a quote
or a documented terminal status, never a silent failure.

Built for the Ontario All-Quote Agent Challenge hackathon. Personal use only — see
[Safety and scope](#safety-and-scope).

## Architecture

```
intake (consent-aware) → market registry → route planner →
browser/voice execution agents → evidence store → normalizer →
coverage ledger / comparison output
```

## Data files

- `data/intake.json` (gitignored — real applicant data, never committed). See Setup below.
- `data/registry.json` — market map / metadata about target rate sources. No personal data.
- `data/results.json` — one entry per quote attempt, each with a required status and evidence.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -e ".[dev]"
playwright install
```

Copy `data/intake.example.json` to `data/intake.json` and fill in your own real information
(gitignored, never committed). Copy `.env.example` to `.env` and add a real `ANTHROPIC_API_KEY`
— required for the LLM steps: mapping an unrecognized form label to a schema field, extracting
structured data from a pasted quote page, and summarizing a failure into one plain-English line.

## Running the app

**Dashboard.** Serves the static `web/` files plus the paste-quote and delete API routes (a plain
`python -m http.server` only gives you the static files, not those two routes):

```bash
python scripts/local_server.py            # http://localhost:8123/web/index.html
```

From there, `web/get-quote.html` is a demo intake wizard, and `web/paste-quote.html` lets you
paste the visible text of any quote-result page (single insurer or a multi-insurer aggregator
page) to run it through the same extract → deterministic-compare pipeline a live automated
result would. Each card's Delete button removes that result and its evidence file for good — the
one-click delete the challenge brief requires.

**Live automation.**

```bash
python scripts/run.py                                  # every in-scope registry source
python scripts/run_dedicated.py                         # just the dedicated flows (Aviva, Onlia), headless
python scripts/run_dedicated.py --headed                # same, with a real visible browser window
python scripts/run_dedicated.py --headed --only aviva-direct
```

`run.py` overwrites `data/results.json` with whatever it attempts that run; `run_dedicated.py`
merges into the existing file instead, leaving results from other sources (e.g. pasted quotes)
untouched. `--headed` matters if you want to actually watch it run — each flow defaults to
headless, which some sites' bot detection treats differently (see `aviva.py`/`onlia.py`).

**Read-only routing preview** — no browser, no network call, no write to `results.json`:

```bash
python scripts/show_route_plan.py
```

**Tests:**

```bash
pytest
```

## Safety and scope

This is a personal-use hackathon prototype, not a commercial product. It only ever acts on the
developer's own real information, never submits payment or binds a policy, never bypasses
CAPTCHAs or access controls, and never fabricates or reuses another person's identity or
licence number. See the project's architecture and safety note (added closer to submission) for
full detail.
