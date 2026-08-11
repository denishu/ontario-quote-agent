"""The real LLM-backed fallback for resolve_field(), used only when a
label doesn't match anything in the alias table. Requires
ANTHROPIC_API_KEY. Kept separate from resolve.py so the alias-matching
path never depends on network access or an API key.

Uses Haiku, not Sonnet -- this is a single-label classification against a
fixed, short list of known fields, not a task that needs deeper reasoning,
and it runs once per unmatched label (with the result meant to be cached
back into the alias table), so keeping it cheap matters.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

from quote_agent.mapping.fields import FIELDS

load_dotenv()

_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT = (
    "You map a single insurance-quote form field's label to a known field "
    "path in a fixed schema. You are given the exact label text and the "
    "full list of valid field paths with descriptions. Respond with only "
    "the matching field path, exactly as given, or the literal string "
    "'no_match' if none of the fields describe what this label is asking "
    "for. Never invent a field path that is not in the provided list. "
    "Respond with the bare answer only -- no explanation, no reasoning, "
    "nothing else on any line.\n\n"
    "Some labels describe a UI control that changes *how* the form is "
    "navigated or *which* question comes next, rather than asking the "
    "applicant to actually provide a piece of data -- e.g. a toggle "
    "letting them choose 'search by year/make/model' vs. 'search by VIN' "
    "to look up their car. Those are not data fields, even if their "
    "wording happens to overlap with a real field's name (a search-method "
    "toggle mentioning 'year, make, model' is not the same as being asked "
    "for the year, make, or model itself). Respond 'no_match' for these, "
    "not your closest guess."
)


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=api_key)


def llm_resolve_field(label: str) -> str | None:
    """Ask Claude which known field a form label maps to. Returns None for
    a 'no_match' response. resolve_field() separately validates that
    whatever comes back is actually a known field path -- this function
    just talks to the API.

    Only the first line of the response is treated as the answer, even
    though the prompt asks for a bare answer with nothing else -- confirmed
    that Haiku doesn't reliably follow that instruction on its own (it
    would sometimes add a rationale paragraph after "no_match" on a blank
    line), which would otherwise make the "no_match" sentinel check fail
    and let a whole explanation sentence through as if it were a field
    path. Trusting the instruction alone isn't enough; the parsing has to
    be robust to it being ignored.
    """
    field_list = "\n".join(f"- {f.path}: {f.description}" for f in FIELDS)
    message = _client().messages.create(
        model=_MODEL,
        max_tokens=64,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Known fields:\n{field_list}\n\nForm field label: {label!r}",
            }
        ],
    )
    answer = message.content[0].text.strip().splitlines()[0].strip()
    return None if answer == "no_match" else answer
