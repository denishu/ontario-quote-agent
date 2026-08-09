from typing import Literal

from pydantic import BaseModel, Field

IncludedStatus = Literal["included", "excluded", "unavailable", "unknown"]


class CoverageConfig(BaseModel):
    """A coverage configuration: either the benchmark requested of every
    source, or the coverage actually returned by one source. Diffing two
    instances of this model field-by-field is the whole normalizer.
    """

    effective_date: str  # ISO 8601 date
    term_months: int = 12
    third_party_liability_limit: int  # e.g. 2_000_000
    dcpd_included: bool
    dcpd_deductible: float | None = None
    accident_benefits_mandatory: bool = True
    optional_benefits: dict[str, IncludedStatus] = Field(default_factory=dict)
    uninsured_automobile_included: bool | None = None
    collision_deductible: float | None = None
    comprehensive_deductible: float | None = None
    all_perils_deductible: float | None = None
    endorsements: list[str] = Field(default_factory=list)  # e.g. ["OPCF44R"]
    telematics_opt_in: bool = False


class Discount(BaseModel):
    name: str
    applied: bool
    conditional_on: str | None = None  # e.g. "bundle", "membership", "telematics"
