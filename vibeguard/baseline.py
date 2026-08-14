"""Baseline file support for classifying existing findings.

Legacy callers may still use :func:`filter_baselined`, but governed/native
evidence should use :func:`record_baselined` so a baseline changes disposition
state without deleting the underlying finding occurrence (issue #132).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from vibeguard.dispositions import DispositionAuthority, FindingRecord, baseline_record
from vibeguard.models import Finding


class BaselineLoadError(Exception):
    """Raised when a baseline file cannot be parsed or validated."""


class BaselineEntry(BaseModel):
    """A single entry in the baseline file.

    The original v1 fields remain valid. Optional governance metadata is additive
    so existing baseline files keep loading while new files can preserve the
    review trail needed by governed dispositions. ``authority`` is evidence,
    never inferred from the fact that an entry exists.
    """

    rule_id: str
    path: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = "carried by repository baseline"
    authority: DispositionAuthority | None = None
    owner: str | None = None
    reviewer: str | None = None
    source_commit: str | None = None
    config_digest: str | None = None

    def created_datetime(self) -> datetime:
        """Return ``created_at`` as a timezone-aware datetime."""
        text = self.created_at
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(text)
        except ValueError as exc:
            raise BaselineLoadError(
                f"baseline created_at is not valid ISO-8601: {self.created_at!r}"
            ) from exc
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Baseline(BaseModel):
    """The complete baseline: a mapping of fingerprint -> entry metadata."""

    version: int = 1
    entries: dict[str, BaselineEntry] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Baseline:
        """Load a baseline from a JSON file.

        Raises ``BaselineLoadError`` if the file is malformed or fails schema
        validation. A missing file is not an error — an empty baseline is
        returned so callers can treat "no baseline" and "empty baseline" the
        same way.
        """
        if not path.exists():
            return cls()
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BaselineLoadError(f"Baseline file {path} is not valid JSON: {exc}") from exc
        try:
            return cls.model_validate(data)
        except Exception as exc:
            raise BaselineLoadError(
                f"Baseline file {path} does not match the expected schema: {exc}"
            ) from exc

    def save(self, path: Path) -> None:
        """Save a baseline to a JSON file."""
        path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def contains(self, fingerprint: str) -> bool:
        """Check if a fingerprint is in the baseline."""
        return fingerprint in self.entries


def compute_fingerprint(finding: Finding) -> str:
    """Compute a stable fingerprint for a finding.

    Thin wrapper around ``Finding.fingerprint`` (the same algorithm) so the
    baseline file, SARIF ``partialFingerprints``, diagnostics reporter, and
    ``model_dump`` JSON all share one identity definition.
    """
    return finding.fingerprint


def create_baseline(findings: list[Finding]) -> Baseline:
    """Create a baseline from a list of findings."""
    entries: dict[str, BaselineEntry] = {}
    for finding in findings:
        fp = compute_fingerprint(finding)
        if fp not in entries:
            entries[fp] = BaselineEntry(
                rule_id=finding.id,
                path=finding.path.replace("\\", "/"),
            )
    return Baseline(entries=entries)


def record_baselined(
    findings: list[Finding],
    baseline: Baseline,
    *,
    accepted: bool,
    rejection_reason: str | None = None,
) -> list[FindingRecord]:
    """Return every finding with matching baselines as separate dispositions.

    Unlike :func:`filter_baselined`, this function never removes an occurrence.
    The caller must explicitly state whether the governing policy accepted the
    baseline. ``accepted=False`` leaves the finding active while retaining the
    attempted disposition as evidence.
    """
    records: list[FindingRecord] = []
    for finding in findings:
        entry = baseline.entries.get(compute_fingerprint(finding))
        if entry is None:
            records.append(FindingRecord(finding=finding))
            continue
        records.append(
            baseline_record(
                finding,
                created_at=entry.created_datetime(),
                reason=entry.reason,
                authority=entry.authority,
                owner=entry.owner,
                reviewer=entry.reviewer,
                source_commit=entry.source_commit,
                config_digest=entry.config_digest,
                accepted=accepted,
                rejection_reason=rejection_reason,
            )
        )
    return records


def filter_baselined(findings: list[Finding], baseline: Baseline) -> list[Finding]:
    """Legacy actionable-only view of findings not present in the baseline.

    This function is retained for compatibility with current CLI behavior while
    #132 is wired through every output surface. It is **not** the native evidence
    representation: governed consumers should call :func:`record_baselined` and
    retain all occurrences.
    """
    return [f for f in findings if not baseline.contains(compute_fingerprint(f))]


__all__ = [
    "Baseline",
    "BaselineEntry",
    "BaselineLoadError",
    "compute_fingerprint",
    "create_baseline",
    "filter_baselined",
    "record_baselined",
]
