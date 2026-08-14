"""Tests for governed, non-destructive finding dispositions (#132)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vibeguard.baseline import Baseline, BaselineEntry, compute_fingerprint, record_baselined
from vibeguard.dispositions import (
    Disposition,
    DispositionAuthority,
    DispositionSource,
    DispositionStatus,
    FindingRecord,
    disposition_decision,
)
from vibeguard.models import Confidence, Finding, Severity


def _finding() -> Finding:
    return Finding(
        id="SEC-TEST",
        rule="test_rule",
        title="Test finding",
        description="synthetic",
        severity=Severity.HIGH,
        path="src/app.py",
        line=7,
        evidence="danger()",
        recommendation="remove danger",
        confidence=Confidence.HIGH,
    )


def test_baseline_preserves_occurrence_and_records_disposition() -> None:
    finding = _finding()
    created = datetime(2026, 8, 1, tzinfo=timezone.utc)
    baseline = Baseline(
        entries={
            compute_fingerprint(finding): BaselineEntry(
                rule_id=finding.id,
                path=finding.path,
                created_at=created.isoformat(),
                reason="accepted existing risk",
                authority=DispositionAuthority.MAINTAINER,
                owner="maintainer@example.test",
                reviewer="security@example.test",
                source_commit="abc123",
                config_digest="sha256:deadbeef",
            )
        }
    )

    records = record_baselined([finding], baseline, accepted=True)

    assert len(records) == 1
    record = records[0]
    assert record.finding == finding
    assert record.fingerprint == finding.fingerprint
    assert record.effective_status == DispositionStatus.BASELINED
    assert disposition_decision(record) == "accepted"
    assert record.disposition is not None
    assert record.disposition.reason == "accepted existing risk"
    assert record.disposition.authority == DispositionAuthority.MAINTAINER
    assert record.disposition.owner == "maintainer@example.test"
    assert record.disposition.reviewer == "security@example.test"
    assert record.disposition.source_commit == "abc123"
    assert record.disposition.config_digest == "sha256:deadbeef"


def test_legacy_baseline_does_not_invent_authority() -> None:
    finding = _finding()
    baseline = Baseline(
        entries={
            compute_fingerprint(finding): BaselineEntry(
                rule_id=finding.id,
                path=finding.path,
            )
        }
    )

    record = record_baselined([finding], baseline, accepted=True)[0]

    assert record.disposition is not None
    assert record.disposition.authority is None
    assert record.effective_status == DispositionStatus.BASELINED
    # A caller may deliberately preserve legacy compatibility, but the evidence
    # remains explicit that no authority was recorded for a future integrity gate.
    assert disposition_decision(record) == "accepted"


def test_rejected_baseline_attempt_does_not_deactivate_finding() -> None:
    finding = _finding()
    baseline = Baseline(
        entries={
            compute_fingerprint(finding): BaselineEntry(
                rule_id=finding.id,
                path=finding.path,
                reason="same-change baseline edit",
            )
        }
    )

    record = record_baselined(
        [finding],
        baseline,
        accepted=False,
        rejection_reason="baseline came from the untrusted change",
    )[0]

    assert record.finding == finding
    assert record.effective_status == DispositionStatus.ACTIVE
    assert record.is_actionable is True
    assert disposition_decision(record) == "rejected"
    assert record.disposition is not None
    assert record.disposition.rejection_reason == "baseline came from the untrusted change"


def test_missing_baseline_entry_is_active_and_still_present() -> None:
    finding = _finding()
    record = record_baselined([finding], Baseline(), accepted=False)[0]

    assert isinstance(record, FindingRecord)
    assert record.finding == finding
    assert record.disposition is None
    assert record.effective_status == DispositionStatus.ACTIVE
    assert disposition_decision(record) == "none"


def test_non_active_disposition_requires_reason() -> None:
    with pytest.raises(ValidationError, match="non-active dispositions require"):
        Disposition(
            status=DispositionStatus.SUPPRESSED,
            source=DispositionSource.REPOSITORY,
            accepted=True,
        )


def test_rejected_disposition_never_deactivates_when_constructed_directly() -> None:
    record = FindingRecord(
        finding=_finding(),
        disposition=Disposition(
            status=DispositionStatus.RISK_ACCEPTED,
            source=DispositionSource.OUT_OF_BAND,
            reason="authority check rejected this request",
            accepted=False,
            rejection_reason="missing independent approval",
        ),
    )

    assert record.effective_status == DispositionStatus.ACTIVE
    assert record.is_actionable is True
    assert disposition_decision(record) == "rejected"


def test_accepted_disposition_cannot_also_have_rejection_reason() -> None:
    with pytest.raises(ValidationError, match="cannot also have rejection_reason"):
        Disposition(
            status=DispositionStatus.SUPPRESSED,
            source=DispositionSource.REPOSITORY,
            reason="reviewed exception",
            accepted=True,
            rejection_reason="contradictory",
        )


def test_expired_disposition_becomes_actionable_again() -> None:
    now = datetime.now(timezone.utc)
    record = FindingRecord(
        finding=_finding(),
        disposition=Disposition(
            status=DispositionStatus.SUPPRESSED,
            source=DispositionSource.REPOSITORY,
            reason="temporary exception",
            accepted=True,
            created_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        ),
    )

    assert record.effective_status == DispositionStatus.EXPIRED
    assert record.is_actionable is True
    assert disposition_decision(record) == "expired"


def test_expiry_must_follow_creation_even_with_naive_datetime() -> None:
    created = datetime(2026, 8, 14, 12, 0)
    with pytest.raises(ValidationError, match="expires_at must be later"):
        Disposition(
            status=DispositionStatus.SUPPRESSED,
            source=DispositionSource.REPOSITORY,
            reason="invalid lifecycle",
            created_at=created,
            expires_at=created - timedelta(seconds=1),
        )
