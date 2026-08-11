"""weaver-spec ``ArtifactSafetyReport`` exporter (additive interop output).

Maps a VibeGuard :class:`~vibeguard.models.ScanResult` onto the weaver-spec
``ArtifactSafetyReport`` contract so findings can feed downstream Weaver Stack
consumers — most directly *lessonweaver*, which turns repeated findings into
reviewed ``LessonCard``s (see ``docs/interop-lessons.md``).

This is an **additive** export: the native JSON, SARIF, and diagnostics
outputs are unchanged. VibeGuard has **no runtime dependency** on any sibling
project — the export works purely from the serialized scan result.

Contract:
``https://weaver-spec.dev/contracts/v0/extended/artifact_safety_report.schema.json``
A vendored copy of the schema lives at
``docs/weaver/artifact_safety_report.schema.json`` for offline validation; the
field mapping is documented in ``docs/interop-lessons.md``.

weaver-spec also defines a distinct ``FailureCaseArtifact`` Extended contract.
VibeGuard intentionally emits ``ArtifactSafetyReport`` here because this
reporter represents the direct output of an artifact safety gate.
``FailureCaseArtifact`` is a separate downstream failure/replay artifact and
should not replace the report format without a deliberate interoperability
design change.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from vibeguard import __version__
from vibeguard.models import Finding, ScanResult, Severity

# ``$id`` of the upstream contract this export targets.
REPORT_SCHEMA_ID = (
    "https://weaver-spec.dev/contracts/v0/extended/artifact_safety_report.schema.json"
)
_GATE_ID = "vibeguard"
_INFORMATION_URI = "https://github.com/dgenio/vibeguard"


def _now_iso() -> str:
    """Current UTC time as an ISO 8601 ``date-time`` string."""
    return datetime.now(timezone.utc).isoformat()


def _report_id(result: ScanResult) -> str:
    """Deterministic report id derived from the finding fingerprints.

    Stable for an identical set of findings so repeated runs on unchanged code
    yield the same ``report_id`` (handy for downstream dedup), while still
    differing for a distinct finding set. Derived from finding content only —
    the scan path is deliberately excluded so the id does not change between
    machines or checkouts when the findings are identical.
    """
    digest = hashlib.sha256()
    for fp in sorted(f.fingerprint for f in result.findings):
        digest.update(fp.encode("utf-8"))
    return "vibeguard-" + digest.hexdigest()[:32]


def _build_finding(finding: Finding) -> dict[str, Any]:
    """Map a :class:`Finding` to an ``ArtifactSafetyReport`` finding object.

    ``finding_id``/``severity``/``message`` are the contract-required fields;
    the remainder ride along under ``additionalProperties`` (allowed by the
    schema) so a consumer that understands VibeGuard can use them while a
    strict spec consumer ignores them.
    """
    obj: dict[str, Any] = {
        "finding_id": finding.id,
        "severity": finding.severity.value,
        "message": f"{finding.title}: {finding.description}",
        "fingerprint": finding.fingerprint,
        "remediation": finding.recommendation,
        # VibeGuard-specific extras (additionalProperties).
        "rule": finding.rule,
        "path": finding.path.replace("\\", "/"),
        "line": finding.line,
        "tags": list(finding.tags),
        "confidence": finding.confidence.value,
    }
    if finding.evidence:
        obj["evidence"] = finding.evidence
    return obj


def build_report(
    result: ScanResult,
    *,
    threshold: Severity,
    blocking: bool,
    created_at: str | None = None,
    target_ref: str | None = None,
) -> dict[str, Any]:
    """Build the ``ArtifactSafetyReport`` dict for a scan result.

    ``threshold`` is the severity at or above which a finding is blocking;
    ``blocking`` selects the contract ``mode`` (``gate`` → ``blocking``,
    ``scan`` → ``advisory``). ``created_at`` is injectable so tests can assert
    exact output — the contract requires the field, so unlike VibeGuard's other
    reporters this export is timestamped (and therefore not byte-reproducible
    by default).
    """
    blocking_count = sum(1 for f in result.findings if f.severity >= threshold)
    decision = "fail" if blocking_count else "pass"
    summary = (
        f"{len(result.findings)} finding(s); {blocking_count} at or above "
        f"{threshold.value} severity."
    )

    report: dict[str, Any] = {
        "report_id": _report_id(result),
        "gate_id": _GATE_ID,
        "decision": decision,
        "created_at": created_at if created_at is not None else _now_iso(),
        "mode": "blocking" if blocking else "advisory",
        "target_ref": target_ref,
        "summary": summary,
        "findings": [_build_finding(f) for f in result.findings],
        "provenance": {
            "tool": "VibeGuard",
            "version": __version__,
            "information_uri": _INFORMATION_URI,
            "ruleset": "builtin",
        },
        # Echo the contract id this payload targets so a consumer can route it
        # without guessing. Lives under additionalProperties.
        "schema": REPORT_SCHEMA_ID,
    }
    return report


def render_weaver(
    result: ScanResult,
    *,
    threshold: Severity,
    blocking: bool,
    created_at: str | None = None,
    target_ref: str | None = None,
) -> str:
    """Return the ``ArtifactSafetyReport`` as a JSON string."""
    report = build_report(
        result,
        threshold=threshold,
        blocking=blocking,
        created_at=created_at,
        target_ref=target_ref,
    )
    return json.dumps(report, indent=2, default=str)


def print_weaver(
    result: ScanResult,
    *,
    threshold: Severity,
    blocking: bool,
    created_at: str | None = None,
    target_ref: str | None = None,
) -> None:
    """Print the ``ArtifactSafetyReport`` JSON to stdout."""
    print(
        render_weaver(
            result,
            threshold=threshold,
            blocking=blocking,
            created_at=created_at,
            target_ref=target_ref,
        )
    )
