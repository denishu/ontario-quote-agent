from enum import Enum
from typing import Literal

from pydantic import Field

from quote_agent.models.base import StrictModel
from quote_agent.models.coverage import CoverageConfig
from quote_agent.models.registry import DistributionType


class ConsentMode(str, Enum):
    LIVE_QUOTE = "live_quote"
    DISCOVERY = "discovery"
    ESTIMATE_ONLY = "estimate_only"


class Consent(StrictModel):
    timestamp: str  # ISO 8601 datetime
    mode: ConsentMode
    permitted_channels: list[DistributionType] = Field(default_factory=list)
    approved_source_ids: list[str] = Field(default_factory=list)  # registry_ids
    excluded_source_ids: list[str] = Field(default_factory=list)  # registry_ids to always skip
    # legal_underwriter names to never count as a real result, even when a broker or aggregator
    # route only reveals one after a result comes back (e.g. an existing family policy's underwriter)
    avoided_underwriters: list[str] = Field(default_factory=list)
    callback_permission: bool = False
    recording_permission: bool = False


class Identity(StrictModel):
    legal_name: str
    date_of_birth: str  # ISO 8601 date
    gender: str | None = None  # not restricted to a fixed set -- forms vary in the options they offer
    marital_status: str | None = None
    licence_number: str | None = None
    licence_province: str = "ON"
    licence_class: str | None = None
    licence_status: str | None = None  # e.g. "valid", "expired", "suspended" -- wording varies by site
    licensed_since: str | None = None  # ISO 8601 date -- first licensed anywhere (Canada or elsewhere)
    g1_licence_date: str | None = None  # ISO 8601 date -- Ontario graduated licensing milestones
    g2_licence_date: str | None = None
    full_g_licence_date: str | None = None
    is_student_living_away_from_home: bool | None = None  # discount eligibility


class Address(StrictModel):
    street: str
    unit: str | None = None
    city: str
    province: str = "ON"
    postal_code: str
    residence_start_date: str | None = None  # ISO 8601 date


class HouseholdMember(StrictModel):
    name: str
    relationship: str
    licensed: bool
    licence_class: str | None = None


class Vehicle(StrictModel):
    vin: str
    model_year: int
    make: str
    model: str
    ownership: Literal["owned", "leased", "financed"]
    new_or_used_at_purchase: Literal["new", "used"] | None = None
    purchase_or_lease_date: str | None = None  # ISO 8601 date (day is arbitrary if only month/year is known)
    primary_use: Literal["pleasure", "commute", "school", "business", "farm", "commercial"]
    annual_km: int
    commute_one_way_km: float | None = None
    commute_days_per_week: int | None = None
    winter_tires: bool | None = None
    anti_theft_device: bool | None = None
    parking_type: str | None = None  # e.g. "garage", "driveway", "street" -- not restricted, wording varies by site


class AccidentRecord(StrictModel):
    date: str  # ISO 8601 date
    at_fault_percentage: int | None = None
    description: str


class ConvictionRecord(StrictModel):
    date: str  # ISO 8601 date
    description: str


class CancellationRecord(StrictModel):
    date: str  # ISO 8601 date
    reason: str


class LicenceSuspensionRecord(StrictModel):
    date: str  # ISO 8601 date
    description: str


class InsuranceHistory(StrictModel):
    current_insurer: str | None = None
    current_policy_expiry: str | None = None  # ISO 8601 date
    years_continuously_insured: int | None = None  # total years insured anywhere, continuously
    years_with_current_insurer: int | None = None  # distinct from the above -- years with THIS insurer specifically
    reason_for_shopping: str | None = None
    cancellations_last_3_years: list[CancellationRecord] = Field(default_factory=list)
    accidents_last_6_years: list[AccidentRecord] = Field(default_factory=list)
    convictions_last_3_years: list[ConvictionRecord] = Field(default_factory=list)
    licence_suspensions_last_6_years: list[LicenceSuspensionRecord] = Field(default_factory=list)


class IntakeProfile(StrictModel):
    """The applicant's own profile, entered once. This is the input sent
    (subject to per-route data minimization) to every rate source, and the
    `coverage_benchmark` every returned quote gets diffed against.
    """

    consent: Consent
    identity: Identity
    contact_email: str
    contact_phone: str
    address: Address
    household: list[HouseholdMember] = Field(default_factory=list)
    vehicles: list[Vehicle]
    insurance_history: InsuranceHistory
    coverage_benchmark: CoverageConfig
    # Whether the applicant or their spouse/common-law partner already
    # holds a home/condo/tenant policy with the *same* insurer being
    # quoted -- a real, recurring bundling-discount question (confirmed
    # on Aviva), kept generic rather than named after any one insurer.
    has_bundled_property_policy: Literal["no", "i_do", "partner_does"] | None = None
