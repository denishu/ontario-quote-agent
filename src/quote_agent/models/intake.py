from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from quote_agent.models.coverage import CoverageConfig
from quote_agent.models.registry import DistributionType


class ConsentMode(str, Enum):
    LIVE_QUOTE = "live_quote"
    DISCOVERY = "discovery"
    ESTIMATE_ONLY = "estimate_only"


class Consent(BaseModel):
    timestamp: str  # ISO 8601 datetime
    mode: ConsentMode
    permitted_channels: list[DistributionType] = Field(default_factory=list)
    approved_source_ids: list[str] = Field(default_factory=list)  # registry_ids
    callback_permission: bool = False
    recording_permission: bool = False


class Identity(BaseModel):
    legal_name: str
    date_of_birth: str  # ISO 8601 date
    licence_number: str | None = None
    licence_province: str = "ON"
    licence_class: str | None = None
    licensed_since: str | None = None  # ISO 8601 date


class Address(BaseModel):
    street: str
    unit: str | None = None
    city: str
    province: str = "ON"
    postal_code: str
    residence_start_date: str | None = None  # ISO 8601 date


class HouseholdMember(BaseModel):
    name: str
    relationship: str
    licensed: bool
    licence_class: str | None = None


class Vehicle(BaseModel):
    vin: str
    model_year: int
    make: str
    model: str
    ownership: Literal["owned", "leased"]
    primary_use: Literal["pleasure", "commute", "school", "business", "farm", "commercial"]
    annual_km: int
    commute_one_way_km: float | None = None


class AccidentRecord(BaseModel):
    date: str  # ISO 8601 date
    at_fault_percentage: int | None = None
    description: str


class ConvictionRecord(BaseModel):
    date: str  # ISO 8601 date
    description: str


class CancellationRecord(BaseModel):
    date: str  # ISO 8601 date
    reason: str


class InsuranceHistory(BaseModel):
    current_insurer: str | None = None
    current_policy_expiry: str | None = None  # ISO 8601 date
    years_continuously_insured: int | None = None
    reason_for_shopping: str | None = None
    cancellations_last_3_years: list[CancellationRecord] = Field(default_factory=list)
    accidents_last_6_years: list[AccidentRecord] = Field(default_factory=list)
    convictions_last_3_years: list[ConvictionRecord] = Field(default_factory=list)


class IntakeProfile(BaseModel):
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
