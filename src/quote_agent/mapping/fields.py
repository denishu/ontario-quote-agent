"""The canonical list of intake fields a form question can resolve to.

This is the target set for both the alias table and the LLM fallback --
every value either of them can return must be one of these paths. Dot
notation into IntakeProfile; a `[]` segment means "one item of that list,"
since a form asks about one vehicle/household member at a time, not the
list as a whole.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    path: str
    description: str


FIELDS: tuple[FieldSpec, ...] = (
    # Identity
    FieldSpec("identity.legal_name", "Applicant's full legal name"),
    FieldSpec("identity.date_of_birth", "Applicant's date of birth"),
    FieldSpec("identity.gender", "Applicant's gender, as offered by the form's own options"),
    FieldSpec("identity.marital_status", "Single, married, common law, etc."),
    FieldSpec("identity.licence_number", "Applicant's driver's licence number"),
    FieldSpec("identity.licence_province", "Province the driver's licence was issued in"),
    FieldSpec("identity.licence_class", "Licence class, e.g. G1, G2, G"),
    FieldSpec("identity.licence_status", "Licence status, e.g. valid, suspended, expired"),
    FieldSpec("identity.licensed_since", "Date first licensed anywhere (Canada or elsewhere)"),
    FieldSpec("identity.g1_licence_date", "Date the G1 licence was obtained in Canada"),
    FieldSpec("identity.g2_licence_date", "Date the G2 licence was obtained in Canada"),
    FieldSpec("identity.full_g_licence_date", "Date the full G licence was obtained in Canada"),
    FieldSpec(
        "identity.is_student_living_away_from_home",
        "Whether the applicant is a university/college student living away from home (discount eligibility)",
    ),
    # Contact
    FieldSpec("contact_email", "Applicant's email address"),
    FieldSpec("contact_phone", "Applicant's phone number"),
    # Address
    FieldSpec("address.street", "Street address"),
    FieldSpec("address.unit", "Unit or apartment number"),
    FieldSpec("address.city", "City"),
    FieldSpec("address.province", "Province"),
    FieldSpec("address.postal_code", "Postal code"),
    FieldSpec("address.residence_start_date", "Date the applicant started living at this address"),
    # Household member (context: one specific additional driver)
    FieldSpec("household[].name", "An additional household driver's name"),
    FieldSpec("household[].relationship", "That household member's relationship to the applicant"),
    FieldSpec("household[].licensed", "Whether that household member is licensed"),
    FieldSpec("household[].licence_class", "That household member's licence class"),
    # Vehicle (context: one specific vehicle being quoted)
    FieldSpec("vehicles[].vin", "Vehicle identification number"),
    FieldSpec("vehicles[].model_year", "Vehicle model year"),
    FieldSpec("vehicles[].make", "Vehicle make/manufacturer"),
    FieldSpec("vehicles[].model", "Vehicle model"),
    FieldSpec("vehicles[].ownership", "Owned, leased, or financed"),
    FieldSpec("vehicles[].new_or_used_at_purchase", "Whether the vehicle was new or used at purchase"),
    FieldSpec("vehicles[].purchase_or_lease_date", "Date the vehicle was purchased or leased"),
    FieldSpec("vehicles[].primary_use", "Pleasure, commute, school, business, farm, or commercial use"),
    FieldSpec("vehicles[].annual_km", "Annual kilometres driven"),
    FieldSpec("vehicles[].commute_one_way_km", "One-way commute distance in km"),
    FieldSpec("vehicles[].winter_tires", "Whether the vehicle has winter tires"),
    FieldSpec("vehicles[].anti_theft_device", "Whether the vehicle has an anti-theft device"),
    FieldSpec("vehicles[].parking_type", "Where the vehicle is parked overnight, e.g. garage, driveway, street"),
    # Insurance and driving history
    FieldSpec("insurance_history.current_insurer", "Current auto insurer name"),
    FieldSpec("insurance_history.current_policy_expiry", "Current policy's expiry date"),
    FieldSpec(
        "insurance_history.years_continuously_insured",
        "Total years continuously insured anywhere (not necessarily with the current insurer)",
    ),
    FieldSpec(
        "insurance_history.years_with_current_insurer",
        "Years insured specifically with the current/most recent insurer",
    ),
    FieldSpec("insurance_history.reason_for_shopping", "Why the applicant is shopping for a new quote"),
    FieldSpec(
        "insurance_history.cancellations_last_3_years",
        "Count or list of prior insurance cancellations in the last 3 years",
    ),
    FieldSpec(
        "insurance_history.accidents_last_6_years",
        "Count or list of accidents/claims (any lookback the form asks for -- not limited to exactly 6 years)",
    ),
    FieldSpec(
        "insurance_history.convictions_last_3_years",
        "Count or list of driving convictions/tickets in the last 3 years",
    ),
    FieldSpec(
        "insurance_history.licence_suspensions_last_6_years",
        "Count or list of driver's licence suspensions in the last 6 years",
    ),
    # Coverage benchmark -- what the applicant is requesting, not a fact about them
    FieldSpec("coverage_benchmark.effective_date", "Requested policy start/effective date"),
    FieldSpec("coverage_benchmark.third_party_liability_limit", "Requested third-party liability limit"),
    FieldSpec("coverage_benchmark.dcpd_included", "Whether Direct Compensation-Property Damage is requested"),
    FieldSpec("coverage_benchmark.collision_deductible", "Requested collision deductible"),
    FieldSpec("coverage_benchmark.comprehensive_deductible", "Requested comprehensive deductible"),
    FieldSpec("coverage_benchmark.all_perils_deductible", "Requested all-perils deductible"),
    FieldSpec("coverage_benchmark.telematics_opt_in", "Whether the applicant is opting into a telematics program"),
)

FIELD_PATHS: frozenset[str] = frozenset(f.path for f in FIELDS)
