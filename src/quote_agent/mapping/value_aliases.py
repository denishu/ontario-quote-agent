"""Known stored-value -> real-world display-text variants, for the small
set of schema fields with a fixed Literal set of values (Vehicle.ownership,
Vehicle.primary_use, Vehicle.new_or_used_at_purchase). Mirrors the field
alias table's design: cheap and deterministic, covering the cases we've
actually hit ("commute" stored, "Commuting" displayed) rather than
matching every value blind and hoping the substring check happens to work.

Only entries that need remapping are listed -- e.g. "pleasure" already
matches "Pleasure" case-insensitively via plain substring matching, so it
has no entry here.
"""

from playwright.sync_api import Locator

VALUE_ALIASES: dict[str, list[str]] = {
    "commute": ["commuting"],
    "owned": ["own"],
    "leased": ["lease"],
    "financed": ["finance"],
    # Boolean fields (e.g. winter_tires, anti_theft_device) get stringified
    # as Python's own str(bool) -- "True"/"False", capitalized exactly like
    # this -- but real sites display "Yes"/"No" for the same question,
    # confirmed on a real site (Aviva). Keys must match that exact case;
    # get_by_text's own matching against the page is case-insensitive, but
    # this dict lookup is a plain Python dict access, which isn't.
    "True": ["Yes"],
    "False": ["No"],
}


def resolve_display_value(scope: Locator, value: str) -> str:
    """Try `value` directly against `scope` (a Playwright Locator), then
    each known alias, returning whichever one actually has a matching
    element. Falls back to `value` unchanged if nothing matches, so the
    caller's own error reflects what was really attempted rather than a
    silently-substituted alias.
    """
    for candidate in (value, *VALUE_ALIASES.get(value, [])):
        if scope.get_by_text(candidate, exact=False).count() > 0:
            return candidate
    return value
