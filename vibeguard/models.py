"""Pydantic models for VibeGuard findings and scan context."""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

if TYPE_CHECKING:
    # Type-only import: rules read ``context.config.<section>`` on every scan,
    # so the field carries a real static type for mypy and editors. The import
    # is guarded because ``vibeguard.config`` imports ``Severity`` from this
    # module at runtime — a runtime import here would be circular. The forward
    # reference is resolved by ``ScanContext.model_rebuild(...)`` at the end of
    # ``vibeguard/config.py``, once ``VibeGuardConfig`` exists (#217, #189).
    from vibeguard.config import VibeGuardConfig


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __lt__(self, other: Severity) -> bool:  # type: ignore[override]
        return _SEVERITY_ORDER[self] < _SEVERITY_ORDER[other]

    def __le__(self, other: Severity) -> bool:  # type: ignore[override]
        return _SEVERITY_ORDER[self] <= _SEVERITY_ORDER[other]

    def __gt__(self, other: Severity) -> bool:  # type: ignore[override]
        return _SEVERITY_ORDER[self] > _SEVERITY_ORDER[other]

    def __ge__(self, other: Severity) -> bool:  # type: ignore[override]
        return _SEVERITY_ORDER[self] >= _SEVERITY_ORDER[other]


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RemediationKind(str, Enum):
    """How a finding's suggested fix is applied (#238).

    The kinds are deliberately mechanical and narrow — VibeGuard only attaches
    structured remediation when the edit is safe to apply or propose without
    re-deriving it from prose. ``MANUAL`` covers fixes that need human judgement
    (the default when no precise edit is known).
    """

    DELETE_FILE = "delete-file"
    ADD_LINE = "add-line"
    REPLACE_SPAN = "replace-span"
    ADD_IGNORE_ENTRY = "add-ignore-entry"
    MANUAL = "manual"


class Remediation(BaseModel):
    """Structured, machine-actionable fix metadata for a :class:`Finding` (#238).

    Optional and absent by default. When present it lets coding agents and
    code-review bots apply or propose a fix without parsing the prose
    ``recommendation``. The SARIF reporter maps the precise in-file edit kinds
    (``add-line``/``replace-span``) to SARIF ``fixes``; ``add-ignore-entry``,
    ``delete-file`` and ``manual`` can't be expressed as an in-file region edit
    and ride along in the JSON output only. The JSON reporter emits the object
    verbatim for every kind. Apply logic itself is out of scope here (deferred
    to the ``vibeguard fix`` work, #152) — this is the shared data model both
    the export side and a future apply side consume.
    """

    kind: RemediationKind = Field(description="How the fix is applied")
    target: str | None = Field(
        default=None,
        description="Relative path the fix edits (defaults to the finding path when omitted)",
    )
    line: int | None = Field(
        default=None, description="1-based line the fix applies to, when known"
    )
    content: str | None = Field(
        default=None, description="Suggested text to add or the replacement span"
    )
    description: str = Field(description="Human-readable summary of the fix")
    confidence: Confidence = Field(
        default=Confidence.MEDIUM,
        description="How safe this fix is to apply automatically",
    )


class Finding(BaseModel):
    """A single finding produced by a VibeGuard rule."""

    id: str = Field(description="Unique finding identifier, e.g. SEC001")
    rule: str = Field(description="Rule name that produced this finding")
    title: str = Field(description="Short human-readable title")
    description: str = Field(description="Detailed description of the issue")
    severity: Severity
    path: str = Field(description="Relative file path")
    line: int | None = Field(default=None, description="Line number if available")
    evidence: str | None = Field(default=None, description="Snippet of offending content")
    recommendation: str = Field(description="How to fix or address this finding")
    tags: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    remediation: Remediation | None = Field(
        default=None,
        description="Optional structured, machine-actionable fix metadata (#238)",
    )

    @field_validator("path", mode="after")
    @classmethod
    def _normalize_path_separators(cls, v: str) -> str:
        # Finding paths are ``/``-separated on every OS (stability contract, #167).
        # A Windows-produced backslash path would break SARIF consumers and make
        # baselines/fingerprints non-portable across machines, so normalize at the
        # model boundary — every rule and reporter inherits the guarantee.
        return v.replace("\\", "/")

    @field_validator("evidence", mode="before")
    @classmethod
    def _truncate_evidence(cls, v: Any) -> Any:
        # Limit evidence length to avoid inadvertently storing long secrets.
        # Documented in ``docs/output-schemas.md``: the fingerprint hashes the
        # stored (post-truncation) evidence, so two findings whose evidence
        # shares the first 200 chars and matches on id+path collide. The
        # ``id`` + ``path`` discriminators keep this narrow in practice.
        if isinstance(v, str) and len(v) > 200:
            return v[:200] + "…"
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fingerprint(self) -> str:
        """Deterministic identity for this finding across runs.

        Algorithm (``vibeguard/v1``):
        ``sha256(finding_id + ":" + normalized_path + ":" + sha256(evidence)[:16])``

        ``evidence`` here is the **stored** evidence — i.e. the 200-char
        snippet after ``_truncate_evidence`` runs. Two findings whose evidence
        shares the same first 200 chars and matches on ``id`` and ``path``
        will collide; in practice the discriminator strength of
        ``id`` + ``path`` keeps that boundary narrow. Line numbers are
        intentionally excluded so a finding's identity is stable when
        surrounding code shifts. See ``docs/output-schemas.md``.
        """
        evidence_part = ""
        if self.evidence:
            evidence_part = hashlib.sha256(self.evidence.encode("utf-8")).hexdigest()[:16]
        raw = f"{self.id}:{self.path.replace(chr(92), '/')}:{evidence_part}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class HealthScore(BaseModel):
    """Deterministic repository health score derived from scan findings.

    The score starts at ``100`` and is reduced by a fixed integer penalty per
    finding based on its severity. The formula and weights are intentionally
    simple and documented in ``docs/output-schemas.md`` so consumers can
    explain the number to their teams without inspecting code.
    """

    total: int = Field(description="Score from 0 (worst) to 100 (best)", ge=0, le=100)
    grade: Literal["A", "B", "C", "D", "F"] = Field(description="Letter grade derived from total")
    penalty: int = Field(description="Sum of severity weights subtracted from 100", ge=0)
    by_severity: dict[str, int] = Field(
        default_factory=dict, description="Finding count per severity level"
    )
    by_category: dict[str, int] = Field(
        default_factory=dict, description="Finding count per rule (category)"
    )
    weights: dict[str, int] = Field(
        default_factory=dict, description="Severity → penalty weight used for this score"
    )


class ScanDiagnostic(BaseModel):
    """A non-finding event recorded during a scan (#195).

    Distinguishes the operationally different things that used to be flattened
    into ``ScanResult.errors`` strings — a routine binary-file skip versus a
    rule crash versus a degraded git context versus a failed network lookup — so
    machine consumers (CI wrappers, the weaver export, ``gate --strict-errors``)
    can react per category instead of regex-matching prose. The taxonomy is
    deliberately small (five categories) and is extended, never renamed, once
    published; see ``docs/output-schemas.md``.

    ``severity`` separates routine information (``info`` — e.g. a binary file
    skipped, which is expected) from a degraded run (``warning``/``error`` — e.g.
    an unreadable file or a crashed rule). ``gate --strict-errors`` keys off this
    distinction so routine skips never fail a build (#218).
    """

    category: Literal["skipped_file", "plugin_load", "git_context", "rule_error", "network"] = (
        Field(description="What kind of event this diagnostic records")
    )
    severity: Literal["info", "warning", "error"] = Field(
        default="warning", description="Operational severity of the diagnostic"
    )
    message: str = Field(description="Human-readable, single-line summary")
    path: str | None = Field(default=None, description="Relative file path, when the event has one")
    rule: str | None = Field(default=None, description="Rule or plugin id, when applicable")
    detail: str | None = Field(default=None, description="Machine-friendly cause/category detail")


#: Diagnostic categories that mean the scan ran *degraded* — the tool could not
#: run as intended (a rule crashed, a plugin failed to load, the git context was
#: unavailable in ``--diff`` mode, or an opt-in registry lookup failed). Routine
#: ``skipped_file`` diagnostics are excluded here and judged by severity instead
#: (an unreadable file is degraded; a binary/oversize skip is not). ``gate
#: --strict-errors`` fails closed when any degraded diagnostic is present (#218).
STRICT_FAIL_CATEGORIES: frozenset[str] = frozenset(
    {"plugin_load", "git_context", "rule_error", "network"}
)


class ScanResult(BaseModel):
    """Aggregated results from a full scan."""

    findings: list[Finding] = Field(default_factory=list)
    scanned_files: int = 0
    changed_files: int = 0
    scan_path: str = "."
    policy: Literal["relaxed", "balanced", "strict"] = "balanced"
    #: Structured, categorized scan diagnostics (#195). The single source of
    #: truth for non-finding events; ``errors`` is the derived string view.
    diagnostics: list[ScanDiagnostic] = Field(default_factory=list)
    #: Backward-compatible flat list of diagnostic messages (#195). Populated by
    #: the scanner as ``[d.message for d in diagnostics]`` so existing consumers
    #: keep working unchanged while ``diagnostics`` carries the structured form.
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_errors_from_diagnostics(self) -> ScanResult:
        """Keep ``errors`` as the flat view of ``diagnostics`` (#195).

        The two fields must never drift: ``errors`` is documented as
        ``[d.message for d in diagnostics]``. Enforce that at the model boundary
        so any caller — not just the scanner — gets a consistent ``ScanResult``.
        When ``diagnostics`` is non-empty, ``errors`` is derived from it
        (overriding any mismatched value). Legacy ``errors``-only construction
        (no diagnostics) is preserved so existing callers keep working.
        """
        if self.diagnostics:
            object.__setattr__(self, "errors", [d.message for d in self.diagnostics])
        return self

    def by_severity(self, severity: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def has_blocking(self, threshold: Severity) -> bool:
        return any(f.severity >= threshold for f in self.findings)

    def degraded_diagnostics(self) -> list[ScanDiagnostic]:
        """Diagnostics that indicate the scan ran degraded (#218).

        Used by ``gate --strict-errors`` to decide whether to fail closed. A
        diagnostic is degraded when its category is in
        :data:`STRICT_FAIL_CATEGORIES`, or when it is a ``skipped_file`` that is
        more serious than routine (severity above ``info`` — e.g. an unreadable
        or un-stattable file, as opposed to an expected binary/oversize skip).
        """
        out: list[ScanDiagnostic] = []
        for d in self.diagnostics:
            if d.category in STRICT_FAIL_CATEGORIES or (
                d.category == "skipped_file" and d.severity != "info"
            ):
                out.append(d)
        return out

    def counts(self) -> dict[str, int]:
        return {s.value: len(self.by_severity(s)) for s in Severity}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def health_score(self) -> HealthScore:
        """Repo health score derived from the current findings list."""
        # Imported here to avoid a circular import via the reporters/scoring chain.
        from vibeguard.scoring import compute_health_score

        return compute_health_score(self.findings)


class GitMetadata(BaseModel):
    """Git context for a scan."""

    branch: str | None = None
    base_branch: str | None = None
    commit: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    is_available: bool = False
    error: str | None = None
    #: How the changed-file/diff set was resolved in ``--diff`` mode.
    #: ``"merge-base"`` means a base branch was found and the diff is
    #: ``base...HEAD``; ``"head-only"`` means base detection failed and the
    #: diff degraded to ``git diff HEAD`` (uncommitted/staged changes only) —
    #: a narrower scope the scanner surfaces as a diagnostic (#182).
    #: ``"staged"`` means ``--staged`` mode (``git diff --cached``): the scope
    #: is exactly the git index, independent of any base branch (#209).
    diff_strategy: Literal["merge-base", "head-only", "staged"] | None = None
    #: True when the working copy is a shallow clone (``fetch-depth: 1``),
    #: which commonly breaks base-branch detection in CI (#182).
    is_shallow: bool = False
    #: Non-fatal git-context warnings (e.g. an explicit ``--base`` ref that
    #: could not be verified). Surfaced by the scanner alongside scan errors.
    warnings: list[str] = Field(default_factory=list)


class ScanContext(BaseModel):
    """Everything a rule needs to perform a scan."""

    root: Path
    config: VibeGuardConfig
    files: list[Path] = Field(default_factory=list)
    changed_files: list[Path] = Field(default_factory=list)
    git: GitMetadata = Field(default_factory=GitMetadata)
    diff_only: bool = False
    #: Raw unified-diff text for the change set, populated by the scanner in
    #: ``--diff`` mode (empty in full-scan mode). Rules that need before/after
    #: information a single file snapshot cannot provide — e.g. detecting a
    #: *lowered* coverage threshold or a *deleted* test file — read it here.
    #: Line-scoped findings do not need it: the scanner already restricts them
    #: to changed lines via the diff.
    diff_text: str = ""
    #: Sink for rule-emitted scan diagnostics (#191). Rules MUST NOT raise and
    #: normally only return :class:`Finding` objects, but a rule with an opt-in
    #: networked check (the reference case is ``slopsquat``'s registry lookup)
    #: may append a :class:`ScanDiagnostic` here to report a degraded run — e.g.
    #: registry lookups that timed out — so the degradation is visible instead
    #: of silently looking like "found nothing". The scanner merges these into
    #: :class:`ScanResult.diagnostics` after all rules run. The same list object
    #: is shared with the per-rule context view, so appends are always seen.
    diagnostics: list[ScanDiagnostic] = Field(default_factory=list)
