"""The single definition of which field paths are sensitive, shared by
every consumer that needs to redact or mask them -- format_fill_report's
text redaction and screenshot.py's visual masking both import this,
rather than each keeping their own copy that could quietly drift apart
from the other over time.
"""

SENSITIVE_PATH_PREFIXES = (
    "identity.legal_name",
    "identity.first_name",
    "identity.last_name",
    "identity.date_of_birth",
    "identity.dob_",  # dob_day/dob_month/dob_year -- split date-of-birth virtual fields
    "identity.licence_number",
    "address.",  # street/unit/postal_code/city -- redact the whole block, not just some of it
    "contact_email",
    "contact_phone",
    "vehicles[].vin",
    "household[].name",
)


def is_sensitive_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in SENSITIVE_PATH_PREFIXES)
