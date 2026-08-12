"""Known field-label -> field-path mappings, seeded from real forms
(ThinkInsure, Onlia) mapped by hand. Keys are already normalized (see
normalize_label in resolve.py) so lookup is a direct hit. This table is
meant to grow every time a new site gets mapped -- most labels should land
here over time, leaving the LLM fallback for genuinely new phrasing.
"""

ALIASES: dict[str, str] = {
    # Identity
    "full name": "identity.legal_name",
    "first name": "identity.first_name",
    "my name is": "identity.first_name",
    "last name": "identity.last_name",
    "my last name is": "identity.last_name",
    "gender": "identity.gender",
    "dob": "identity.date_of_birth",
    "date of birth": "identity.date_of_birth",
    "born": "identity.date_of_birth",
    "single married or common law": "identity.marital_status",
    "marital status": "identity.marital_status",
    "marriage status": "identity.marital_status",
    "driver s licence": "identity.licence_number",
    "driver s license": "identity.licence_number",
    "my driver s licence number is": "identity.licence_number",
    "licence number": "identity.licence_number",
    "license number": "identity.licence_number",
    "driver s licence status": "identity.licence_status",
    "driver s license status": "identity.licence_status",
    "looks like you received your g1 license at this age in canada": "identity.g1_licence_date",
    "how old were you when you got your g2 license in canada": "identity.g2_licence_date",
    "how old were you when you got your full g license in canada": "identity.full_g_licence_date",
    "are you a university or college student currently living away from home": (
        "identity.is_student_living_away_from_home"
    ),
    # Contact
    "email": "contact_email",
    "email address": "contact_email",
    "phone number": "contact_phone",
    # Address
    "postal code": "address.postal_code",
    "my address is": "address.street",
    "please enter and select street address": "address.street",
    "street address": "address.street",
    "province": "address.province",
    # Vehicle
    "vehicle ownership": "vehicles[].ownership",
    "do you currently own lease or finance this vehicle": "vehicles[].ownership",
    "when did you buy or lease": "vehicles[].purchase_or_lease_date",
    "when did you purchase your vehicle": "vehicles[].purchase_or_lease_date",
    "select the month you bought or leased your car": "vehicles[].purchase_month",
    "select the year you bought or leased your car": "vehicles[].purchase_year",
    "select the year that your car was manufactured": "vehicles[].model_year",
    "select the make of your car": "vehicles[].make",
    "select the model of your car": "vehicles[].model",
    "at the time of purchase was your vehicle new or used": "vehicles[].new_or_used_at_purchase",
    "what do you use your vehicle for": "vehicles[].primary_use",
    "vehicle use": "vehicles[].primary_use",
    "what is your daily commute one way in km": "vehicles[].commute_one_way_km",
    "distance to work school or transit one way": "vehicles[].commute_one_way_km",
    "how many km driven per year": "vehicles[].annual_km",
    "annual km": "vehicles[].annual_km",
    "do you have winter tires": "vehicles[].winter_tires",
    "do you have an anti theft device": "vehicles[].anti_theft_device",
    "please specify where your vehicle is parked": "vehicles[].parking_type",
    # Insurance / driving history
    "how many years have you had auto insurance": "insurance_history.years_continuously_insured",
    "years insured": "insurance_history.years_continuously_insured",
    "how many years have you been with your current insurance company": (
        "insurance_history.years_with_current_insurer"
    ),
    "do you have any tickets or convictions in the past 3 years": "insurance_history.convictions_last_3_years",
    "tickets in last 3 years not including parking": "insurance_history.convictions_last_3_years",
    "at fault accidents last 3 years": "insurance_history.accidents_last_6_years",
    "your accidents or claims in the past 10 years": "insurance_history.accidents_last_6_years",
    "times insurance has been cancelled last 3 years": "insurance_history.cancellations_last_3_years",
    "prior insurance cancellations in the last 5 years": "insurance_history.cancellations_last_3_years",
    "do you have licence suspensions in the last 6 years": "insurance_history.licence_suspensions_last_6_years",
    "times license has been suspended last 6 years": "insurance_history.licence_suspensions_last_6_years",
    # Coverage benchmark
    "when would you like your insurance to start": "coverage_benchmark.effective_date",
    "start date": "coverage_benchmark.effective_date",
    "third party liability limit": "coverage_benchmark.third_party_liability_limit",
    "collision deductible": "coverage_benchmark.collision_deductible",
    "comprehensive deductible": "coverage_benchmark.comprehensive_deductible",
    "all perils deductible": "coverage_benchmark.all_perils_deductible",
}
