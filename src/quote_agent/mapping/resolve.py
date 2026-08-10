"""resolve_field(): the single entry point for turning a form field's
label into a known schema field path.

Alias lookup first (fast, free, deterministic, and testable with zero
external dependencies); the LLM fallback is injected by the caller rather
than hardcoded here, so this stays fully unit-testable without an API key.
"""

import re
from typing import Callable

from quote_agent.mapping.aliases import ALIASES
from quote_agent.mapping.fields import FIELD_PATHS

_PUNCTUATION_TO_SPACE = re.compile(r"[’'?:,.()]")
_WHITESPACE = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """Lowercase, strip punctuation that varies harmlessly between sites,
    and collapse whitespace -- so "Driver's Licence" and "driver's
    licence:" both hit the same alias key.
    """
    text = label.strip().lower()
    text = _PUNCTUATION_TO_SPACE.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def resolve_field(
    label: str,
    llm_fallback: Callable[[str], str | None] | None = None,
) -> str | None:
    """Resolve a form field's label to a field path (e.g.
    "identity.licence_class"). Tries the alias table first; falls back to
    llm_fallback only if nothing matches there. Returns None if genuinely
    unresolved -- that's a real schema gap to go add, not a mapping bug.
    """
    key = normalize_label(label)
    if key in ALIASES:
        return ALIASES[key]

    if llm_fallback is None:
        return None

    result = llm_fallback(label)
    if result is not None and result not in FIELD_PATHS:
        raise ValueError(f"LLM fallback returned an unknown field path: {result!r}")
    return result
