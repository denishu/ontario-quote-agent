from enum import Enum

from pydantic import Field, model_validator

from quote_agent.models.base import StrictModel
from quote_agent.models.coverage import CoverageConfig, Discount
from quote_agent.models.status import QUOTE_STATUSES, QuoteStatus


class Confidence(str, Enum):
    HIGH = "high"  # returned exact premium with matching coverage
    MEDIUM = "medium"  # licensed representative's documented quote
    LOW = "low"  # estimate or unresolved coverage difference


class Evidence(StrictModel):
    """Required on every result regardless of status. artifact_ref points
    into evidence/ (gitignored) — never a raw, unredacted capture.
    """

    timestamp: str  # ISO 8601 datetime
    source_url: str | None = None
    public_phone_route: str | None = None
    artifact_ref: str  # redacted screenshot, structured call note, or response reference


class ResultEntry(StrictModel):
    """One attempt against one registry entry. A quote outcome requires a
    premium and coverage; every other outcome requires a failure_reason and
    next_action instead. Evidence is required either way.
    """

    registry_id: str
    status: QuoteStatus
    returned_legal_underwriter: str | None = None  # the underwriter actually named on the quote/disclosure
    premium_annual: float | None = None
    premium_monthly: float | None = None
    returned_coverage: CoverageConfig | None = None
    coverage_variance: list[str] = Field(default_factory=list)  # field names that differ from benchmark
    discounts: list[Discount] = Field(default_factory=list)
    evidence: Evidence
    confidence: Confidence
    failure_reason: str | None = None
    next_action: str | None = None

    @model_validator(mode="after")
    def _check_status_consistency(self) -> "ResultEntry":
        if self.status in QUOTE_STATUSES:
            if self.premium_annual is None or self.returned_coverage is None:
                raise ValueError(
                    f"status={self.status.value} requires premium_annual and returned_coverage"
                )
            if not self.returned_legal_underwriter:
                raise ValueError(f"status={self.status.value} requires returned_legal_underwriter")
        elif self.failure_reason is None:
            raise ValueError(f"status={self.status.value} requires failure_reason")
        return self
