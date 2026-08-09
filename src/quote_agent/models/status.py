from enum import Enum


class QuoteStatus(str, Enum):
    """Terminal status for a single rate-source attempt.

    Shared by RegistryEntry.status (last known status) and ResultEntry.status
    (outcome of one attempt). Every value here must end in evidence, not a
    silent failure.
    """

    QUOTED_COMPARABLE = "quoted_comparable"
    QUOTED_NON_COMPARABLE = "quoted_non_comparable"
    ESTIMATE_ONLY = "estimate_only"
    CALLBACK_REQUIRED = "callback_required"
    MANUAL_HANDOFF = "manual_handoff"
    INELIGIBLE = "ineligible"
    AFFINITY_RESTRICTED = "affinity_restricted"
    SPECIALTY_ONLY = "specialty_only"
    DUPLICATE_RATE_SOURCE = "duplicate_rate_source"
    NOT_CURRENTLY_WRITING = "not_currently_writing"
    BLOCKED = "blocked"
    UNREACHABLE = "unreachable"
    UNRESOLVED = "unresolved"


QUOTE_STATUSES = frozenset({QuoteStatus.QUOTED_COMPARABLE, QuoteStatus.QUOTED_NON_COMPARABLE})
