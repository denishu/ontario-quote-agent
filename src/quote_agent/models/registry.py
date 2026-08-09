from enum import Enum

from pydantic import Field

from quote_agent.models.base import StrictModel
from quote_agent.models.status import QuoteStatus


class DistributionType(str, Enum):
    DIRECT = "direct"
    AGENT = "agent"
    BROKER = "broker"
    AGGREGATOR = "aggregator"
    AFFINITY = "affinity"
    MGA_PROGRAM = "MGA_program"
    MUTUAL = "mutual"
    RESIDUAL = "residual"


class ProductScope(str, Enum):
    STANDARD_PPA = "standard_PPA"
    NONSTANDARD_PPA = "nonstandard_PPA"
    HIGH_NET_WORTH = "high_net_worth"
    COLLECTOR = "collector"
    COMMERCIAL_SPECIALTY = "commercial_specialty"
    UNKNOWN = "unknown"


class Requirement(str, Enum):
    LICENCE = "licence"
    VIN = "VIN"
    MEMBERSHIP = "membership"
    CALLBACK = "callback"
    HUMAN = "human"
    OTHER = "other"


class RegistryEntry(StrictModel):
    """One row of the market map: metadata about a target rate source.
    Research output, produced before any automation runs. Never contains
    applicant data.
    """

    registry_id: str
    last_verified_at: str  # ISO 8601 datetime
    legal_underwriter: str
    insurer_group: str
    brand_or_program: str
    distribution_type: DistributionType
    product_scope: ProductScope
    distinct_rate_source_id: str  # dedup key
    quote_url: str | None = None
    public_phone_route: str | None = None
    licensed_intermediary: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    automation_notes: str | None = None
    status: QuoteStatus = QuoteStatus.UNRESOLVED
    evidence_url: str | None = None
