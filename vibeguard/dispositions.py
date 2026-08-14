"""Non-destructive finding dispositions (issue #132).

A :class:`~vibeguard.models.Finding` is evidence that a rule observed something.
Suppressing, baselining, accepting, or remediating that observation must not
rewrite or delete the observation itself. This module models those lifecycle
judgements separately so native evidence can retain both facts:

* what VibeGuard observed; and
* what an authorised actor decided to do with that observation.

The models are intentionally independent of CLI/gate policy. Enforcement
profiles decide whether a disposition is authoritative; this module preserves
the data needed to make and audit that decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from vibeguard.models import Finding


class DispositionStatus(str, Enum):
    """Lifecycle state applied to an immutable finding occurrence."""

    ACTIVE = "active"
    SUPPRESSED = "suppressed"
    BASELINED = "baselined"
    RISK_ACCEPTED = "risk_accepted"
    FALSE_POSITIVE = "false_positive"
    EXPIRED = "expired"
    REMEDIATED = "remediated"


class DispositionSource(str, Enum):
    """Where a disposition came from."""

    INLINE = "inline"
    REPOSITORY = "repository"
    BASELINE = "baseline"
    OUT_OF_BAND = "out_of_band"
    API = "api"
    LOCAL = "local"


class DispositionAuthority(str, Enum):
    """Authority asserted for a disposition.

    These values record the claimed authority class; repository metadata alone
    is not cryptographic proof of human identity. The integrity profile is
    responsible for deciding whether the assertion is acceptable for the
    requested operation.
    """

    DEVELOPER = "developer"
    CODE_OWNER = "code_owner"
    SECURITY_OWNER = "security_owner"
    MAINTAINER = "maintainer"
    POLICY_OWNER = "policy_owner"
    RISK_OWNER = "risk_owner"
    INDEPENDENT_HUMAN = "independent_human"


class Disposition(BaseModel):
    """A reviewable lifecycle judgement over one finding occurrence."""

    status: DispositionStatus
    source: DispositionSource
    authority: DispositionAuthority | None = None
    owner: str | None = None
    reviewer: str | None = None
    reason: str = ""
    scope: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    linked_issue: str | None = None
    linked_pr: str | None = None
    source_commit: str | None = None
    config_digest: str | None = None
    accepted: bool = False
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _validate_state(self) -> Disposition:
        """Keep acceptance/rejection and lifecycle fields internally coherent."""
        if self.accepted and self.rejection_reason:
            raise ValueError("an accepted disposition cannot also have rejection_reason")
        if self.status != DispositionStatus.ACTIVE and not self.reason.strip():
            raise ValueError("non-active dispositions require a non-empty reason")
        if self.expires_at is not None:
            created = _as_aware_utc(self.created_at)
            expires = _as_aware_utc(self.expires_at)
            if expires <= created:
                raise ValueError("expires_at must be later than created_at")
        return self

    def is_expired(self, *, at: datetime | None = None) -> bool:
        """Return whether this disposition has expired at *at* (UTC now by default)."""
        if self.expires_at is None:
            return False
        now = _as_aware_utc(at if at is not None else datetime.now(timezone.utc))
        return now >= _as_aware_utc(self.expires_at)


def _as_aware_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC for safe comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class FindingRecord(BaseModel):
    """Immutable finding occurrence plus its separate disposition state.

    ``finding`` is never rewritten to represent suppression/baselining. Consumers
    that need only actionable findings may filter on :attr:`effective_status`,
    but native evidence can still serialize every observed occurrence.
    """

    finding: Finding
    disposition: Disposition | None = None

    @property
    def fingerprint(self) -> str:
        """Stable occurrence identity inherited from the finding."""
        return self.finding.fingerprint

    @property
    def effective_status(self) -> DispositionStatus:
        """Return the authoritative lifecycle state without deleting evidence."""
        if self.disposition is None or not self.disposition.accepted:
            return DispositionStatus.ACTIVE
        if self.disposition.is_expired():
            return DispositionStatus.EXPIRED
        return self.disposition.status

    @property
    def is_actionable(self) -> bool:
        """Whether the occurrence remains active for ordinary finding policy."""
        return self.effective_status in {DispositionStatus.ACTIVE, DispositionStatus.EXPIRED}


def baseline_record(
    finding: Finding,
    *,
    created_at: datetime,
    reason: str = "carried by repository baseline",
    authority: DispositionAuthority | None = None,
    owner: str | None = None,
    reviewer: str | None = None,
    source_commit: str | None = None,
    config_digest: str | None = None,
    accepted: bool,
    rejection_reason: str | None = None,
) -> FindingRecord:
    """Return *finding* with a separate baseline disposition.

    Authority is never inferred and acceptance is never defaulted. Callers must
    propagate the authority evidence that actually exists and explicitly state
    whether the selected policy accepted the disposition.
    """
    disposition = Disposition(
        status=DispositionStatus.BASELINED,
        source=DispositionSource.BASELINE,
        authority=authority,
        owner=owner,
        reviewer=reviewer,
        reason=reason,
        created_at=created_at,
        source_commit=source_commit,
        config_digest=config_digest,
        accepted=accepted,
        rejection_reason=rejection_reason,
    )
    return FindingRecord(finding=finding, disposition=disposition)


DispositionDecision = Literal["accepted", "rejected", "expired", "none"]


def disposition_decision(record: FindingRecord) -> DispositionDecision:
    """Return a stable machine-oriented decision label for evidence output."""
    if record.disposition is None:
        return "none"
    if not record.disposition.accepted:
        return "rejected"
    if record.disposition.is_expired():
        return "expired"
    return "accepted"


__all__ = [
    "Disposition",
    "DispositionAuthority",
    "DispositionDecision",
    "DispositionSource",
    "DispositionStatus",
    "FindingRecord",
    "baseline_record",
    "disposition_decision",
]
