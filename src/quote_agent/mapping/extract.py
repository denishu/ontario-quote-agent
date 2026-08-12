"""get_field_value(): given a field path as returned by resolve_field(),
pull the actual value out of an IntakeProfile.

Handles three cases resolve_field() can produce that aren't a plain
attribute lookup:
  - virtual fields (identity.first_name/last_name -- not separately
    stored, derived by splitting legal_name; identity.dob_day/dob_month/
    dob_year -- derived by splitting date_of_birth; vehicles[].
    purchase_month/purchase_year -- not separately stored, derived by
    splitting purchase_or_lease_date)
  - list-item fields (vehicles[].*, household[].* -- need to know which
    item via vehicle_index/household_index)
  - count fields (insurance_history's record lists -- a form usually asks
    "how many," not for the itemized list)
"""

import calendar
from typing import Any

from quote_agent.models import IntakeProfile

_MONTH_NAMES = [calendar.month_name[i] for i in range(1, 13)]

_COUNT_FIELDS = frozenset(
    {
        "insurance_history.cancellations_last_3_years",
        "insurance_history.accidents_last_6_years",
        "insurance_history.convictions_last_3_years",
        "insurance_history.licence_suspensions_last_6_years",
    }
)


def get_field_value(
    intake: IntakeProfile,
    path: str,
    *,
    vehicle_index: int = 0,
    household_index: int = 0,
) -> Any:
    """Return the value at `path` (as resolved by resolve_field()) from
    `intake`. vehicle_index/household_index pick which list item for
    vehicles[].*/household[].* paths -- defaults to the first, since most
    flows fill one vehicle/driver at a time and the caller is expected to
    pass the right index when there's more than one.
    """
    if path == "identity.first_name":
        return intake.identity.legal_name.split(" ", 1)[0]
    if path == "identity.last_name":
        parts = intake.identity.legal_name.split(" ", 1)
        return parts[1] if len(parts) > 1 else ""

    if path == "identity.dob_year":
        return intake.identity.date_of_birth.split("-")[0]
    if path == "identity.dob_month":
        return intake.identity.date_of_birth.split("-")[1]
    if path == "identity.dob_day":
        return intake.identity.date_of_birth.split("-")[2]

    if path == "vehicles[].purchase_month":
        date_str = intake.vehicles[vehicle_index].purchase_or_lease_date
        if date_str is None:
            return None
        month = int(date_str.split("-")[1])
        return _MONTH_NAMES[month - 1]
    if path == "vehicles[].purchase_year":
        date_str = intake.vehicles[vehicle_index].purchase_or_lease_date
        if date_str is None:
            return None
        return int(date_str.split("-")[0])

    if path in _COUNT_FIELDS:
        field_name = path.split(".", 1)[1]
        records = getattr(intake.insurance_history, field_name)
        return len(records)

    if path.startswith("vehicles[]."):
        field_name = path.split(".", 1)[1]
        return getattr(intake.vehicles[vehicle_index], field_name)

    if path.startswith("household[]."):
        field_name = path.split(".", 1)[1]
        return getattr(intake.household[household_index], field_name)

    value: Any = intake
    for segment in path.split("."):
        value = getattr(value, segment)
    return value
