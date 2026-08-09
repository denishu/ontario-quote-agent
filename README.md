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

- `data/intake.json` (gitignored — real applicant data, never committed). Copy
  `data/intake.example.json` to `data/intake.json` and fill in your own information.
- `data/registry.json` — market map / metadata about target rate sources. No personal data.
- `data/results.json` — one entry per quote attempt, each with a required status and evidence.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -e ".[dev]"
playwright install
```

## Safety and scope

This is a personal-use hackathon prototype, not a commercial product. It only ever acts on the
developer's own real information, never submits payment or binds a policy, never bypasses
CAPTCHAs or access controls, and never fabricates or reuses another person's identity or
licence number. See the project's architecture and safety note (added closer to submission) for
full detail.
