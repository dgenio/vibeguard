"""VibeGuard configuration loading and Pydantic models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vibeguard.models import Finding, Severity


class IgnoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(
        default=[
            ".git/",
            "node_modules/",
            ".venv/",
            "venv/",
            "dist/",
            "build/",
            "*.egg-info/",
            ".tox/",
            "__pycache__/",
        ]
    )
    findings: list[str] = Field(default_factory=list)


class PackageAllowlistConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[str] = Field(
        default=[
            "README.md",
            "README.rst",
            "LICENSE",
            "pyproject.toml",
            "setup.cfg",
            "setup.py",
            "package.json",
            "CHANGELOG.md",
            "NOTICE",
        ]
    )


class SecretsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    min_entropy: float = 3.5


class SourcemapsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class PackagingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class DependenciesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class RiskyPatternsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    diff_size_threshold: int = Field(default=30, ge=1)
    diff_breadth_threshold: int = Field(default=5, ge=1)


class TestsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class AIFootprintsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class GoRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class CiDockerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class IaCConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class SqlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class AgentMemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class ScannerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_file_size_kb: int = Field(default=1024, ge=1)


class PluginsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disabled: list[str] = Field(default_factory=list)


class PublishCheckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    ecosystem: str = "auto"
    fail_on: str = "high"


class Suppression(BaseModel):
    """A policy suppression entry in vibeguard.yaml."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str | None = None
    rule_id: str | None = None
    path_pattern: str = "**"
    reason: str
    expires: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be empty")
        return v

    @model_validator(mode="after")
    def _must_have_id(self) -> Suppression:
        if not self.finding_id and not self.rule_id:
            raise ValueError("At least one of finding_id or rule_id is required")
        return self


class SeverityOverride(BaseModel):
    """Override severity for a specific rule or finding."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None
    finding_id: str | None = None
    severity: Severity

    @model_validator(mode="after")
    def _must_have_id(self) -> SeverityOverride:
        if not self.rule_id and not self.finding_id:
            raise ValueError("At least one of rule_id or finding_id is required")
        return self


class VibeGuardConfig(BaseModel):
    """Root configuration model."""

    model_config = ConfigDict(extra="forbid")

    policy: Literal["relaxed", "balanced", "strict"] = "balanced"
    fail_on: Severity = Severity.HIGH
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    package_allowlist: PackageAllowlistConfig = Field(default_factory=PackageAllowlistConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    sourcemaps: SourcemapsConfig = Field(default_factory=SourcemapsConfig)
    packaging: PackagingConfig = Field(default_factory=PackagingConfig)
    dependencies: DependenciesConfig = Field(default_factory=DependenciesConfig)
    risky_patterns: RiskyPatternsConfig = Field(default_factory=RiskyPatternsConfig)
    tests: TestsConfig = Field(default_factory=TestsConfig)
    ai_footprints: AIFootprintsConfig = Field(default_factory=AIFootprintsConfig)
    go_rules: GoRulesConfig = Field(default_factory=GoRulesConfig)
    ci_docker: CiDockerConfig = Field(default_factory=CiDockerConfig)
    iac: IaCConfig = Field(default_factory=IaCConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    sql: SqlConfig = Field(default_factory=SqlConfig)
    agent_memory: AgentMemoryConfig = Field(default_factory=AgentMemoryConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    publish_check: PublishCheckConfig = Field(default_factory=PublishCheckConfig)
    suppressions: list[Suppression] = Field(default_factory=list)
    severity_overrides: list[SeverityOverride] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path | str | None = None) -> VibeGuardConfig:
        """Load config from a YAML file, falling back to defaults."""
        if path is None:
            path = Path("vibeguard.yaml")

        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with config_path.open(encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        return cls.model_validate(data)

    def is_path_ignored(self, path: str | Path) -> bool:
        """Return True if the path matches any ignore pattern."""
        import fnmatch

        path_str = str(path).replace("\\", "/")
        parts = path_str.split("/")
        for pattern in self.ignore.paths:
            # Normalize pattern – strip trailing slash for directory matching
            clean = pattern.rstrip("/")
            # Check individual path components against the pattern
            for part in parts:
                if fnmatch.fnmatch(part, clean):
                    return True
        return False


def load_ignorefile(root: Path) -> list[str]:
    """Load .vibeguardignore patterns from the scan root using pathspec."""
    ignore_path = root / ".vibeguardignore"
    if not ignore_path.exists():
        return []
    return [
        line.strip()
        for line in ignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


DEFAULT_CONFIG_YAML = """\
# VibeGuard configuration
# https://github.com/dgenio/vibeguard

policy: balanced      # relaxed | balanced | strict
fail_on: high         # info | low | medium | high | critical

ignore:
  paths:
    - .git/
    - node_modules/
    - .venv/
    - venv/
    - dist/
    - build/
    - "*.egg-info/"
    - .tox/
    - __pycache__/
  findings: []        # list of finding IDs to suppress

package_allowlist:
  files:
    - README.md
    - README.rst
    - LICENSE
    - pyproject.toml
    - setup.cfg
    - setup.py
    - package.json
    - CHANGELOG.md
    - NOTICE

scanner:
  max_file_size_kb: 1024  # skip files larger than this (KB)

secrets:
  enabled: true
  min_entropy: 3.5

sourcemaps:
  enabled: true

packaging:
  enabled: true

dependencies:
  enabled: true

risky_patterns:
  enabled: true

tests:
  enabled: true

ai_footprints:
  enabled: true
"""


def apply_policy_suppressions(
    findings: list[Finding],
    suppressions: list[Suppression],
) -> tuple[list[Finding], list[Finding]]:
    """Apply policy suppressions to findings.

    Returns (active_findings, warnings) where warnings are synthetic findings
    for expired suppressions.
    """
    from datetime import date
    from fnmatch import fnmatch

    from vibeguard.models import Finding as _Finding

    if not suppressions:
        return findings, []

    active: list[_Finding] = []
    warnings: list[_Finding] = []

    for finding in findings:
        suppressed = False
        for sup in suppressions:
            # Check if this suppression matches the finding
            id_match = False
            if (
                sup.finding_id
                and sup.finding_id == finding.id
                or sup.rule_id
                and sup.rule_id == finding.rule
            ):
                id_match = True
            if not id_match:
                continue

            # Check path pattern
            if not fnmatch(finding.path, sup.path_pattern):
                continue

            # Check expiry
            if sup.expires:
                try:
                    expiry_date = date.fromisoformat(sup.expires)
                except ValueError:
                    continue
                if expiry_date < date.today():
                    warnings.append(
                        _Finding(
                            id="SUPPRESSION-EXPIRED",
                            rule="policy",
                            title=f"Suppression expired for {sup.finding_id or sup.rule_id}",
                            description=f"Suppression expired on {sup.expires}",
                            severity=Severity.INFO,
                            path=finding.path,
                            recommendation="Remove or update the expired suppression.",
                        )
                    )
                    continue

            suppressed = True
            break

        if not suppressed:
            active.append(finding)

    return active, warnings


def apply_severity_overrides(
    findings: list[Finding],
    overrides: list[SeverityOverride],
) -> list[Finding]:
    """Apply severity overrides to findings, returning new list with updated severities."""
    if not overrides:
        return findings

    result: list[Finding] = []
    for finding in findings:
        new_severity: Severity | None = None
        # finding_id overrides take precedence, so apply rule_id first, finding_id last
        for override in overrides:
            if override.rule_id and override.rule_id == finding.rule:
                new_severity = override.severity
        for override in overrides:
            if override.finding_id and override.finding_id == finding.id:
                new_severity = override.severity

        if new_severity is not None and new_severity != finding.severity:
            result.append(finding.model_copy(update={"severity": new_severity}))
        else:
            result.append(finding)

    return result
