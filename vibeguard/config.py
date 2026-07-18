"""VibeGuard configuration loading and Pydantic models."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, get_args

import pathspec
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from vibeguard.models import ScanContext, Severity
from vibeguard.policies import KNOWN_PACK_NAMES, load_policy_pack, merge_policy_pack

if TYPE_CHECKING:
    from vibeguard.models import Finding


@lru_cache(maxsize=128)
def compile_pathspec(patterns: tuple[str, ...]) -> pathspec.PathSpec:
    """Compile gitignore-syntax ``patterns`` into a cached :class:`pathspec.PathSpec`.

    One pattern grammar (gitignore, via ``pathspec``) governs every ignore
    source — ``ignore.paths`` config, ``.vibeguardignore``, and ``.gitignore``
    (#216, #211) — instead of the per-component ``fnmatch`` that used to back
    ``ignore.paths`` and silently never matched multi-segment patterns like
    ``packages/*/build/``.

    Cached on the (hashable) pattern tuple so the scanner can recompile a merged
    ignore set once per scan rather than paying the parse cost for every file.
    """
    return pathspec.PathSpec.from_lines("gitignore", patterns)


PolicyPackName = Literal["oss-library", "web-app", "strict-ci"]

# Guard: the Literal must stay in sync with KNOWN_PACK_NAMES. Python's type
# system cannot derive a Literal from a runtime tuple, so this import-time
# assertion catches drift earlier than tests alone.
assert set(get_args(PolicyPackName)) == set(KNOWN_PACK_NAMES), (
    f"PolicyPackName Literal {set(get_args(PolicyPackName))} does not match "
    f"KNOWN_PACK_NAMES {set(KNOWN_PACK_NAMES)} — update both when adding a pack."
)


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


class SourceTestMapping(BaseModel):
    """Maps a source-file glob to one or more test-file globs.

    Used by :class:`vibeguard.rules.tests.MissingTestsRule` in monorepos
    where the default ``src/ ⇄ tests/`` heuristic would otherwise flag valid
    layouts (e.g. ``packages/api/src/**`` paired with
    ``packages/api/tests/**``) as untested.

    Both ``source`` and ``tests`` accept gitignore-style globs (matched via
    ``pathspec``). At least one ``tests`` glob is required, and patterns
    must be non-empty after stripping whitespace — invalid patterns surface
    as ``ValidationError`` at config load.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Glob matched against changed source files")
    tests: list[str] = Field(
        min_length=1,
        description="One or more globs for the test files that satisfy this source glob",
    )

    @model_validator(mode="after")
    def _patterns_non_empty(self) -> SourceTestMapping:
        if not self.source.strip():
            raise ValueError("'source' must be a non-empty glob pattern")
        for pat in self.tests:
            if not pat.strip():
                raise ValueError("'tests' patterns must not be empty strings")
        return self


class TestsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    mapping: list[SourceTestMapping] = Field(
        default_factory=list,
        description=(
            "Optional source-test path mappings for monorepos. When empty (the "
            "default), the rule uses its built-in heuristics; when populated, a "
            "source change is treated as covered if any mapping's source glob "
            "matches the file AND any of that mapping's test globs is touched "
            "by the same change set."
        ),
    )


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


class SlopsquatConfig(BaseModel):
    """Controls the slopsquatting / hallucinated-dependency rule.

    ``registry_check`` is **off by default and opt-in**: enabling it makes the
    rule perform network I/O against the package registry (PyPI/npm) to verify
    each declared dependency exists and is not brand-new. That deviates from
    VibeGuard's default offline/deterministic contract, so it must be turned on
    explicitly. The offline name-shape heuristic runs regardless.

    Scope of the registry check: **existence** (the package is published) and
    **recency** (``registry_max_age_days``). A download-count / popularity
    signal is intentionally **out of scope** — npm and PyPI expose download
    stats only via separate services (PyPI's JSON API does not expose them at
    all), so a uniform, deterministic-by-default cross-registry popularity check
    is not available here; recency is the registry-side proxy VibeGuard uses for
    the slopsquat-capture window.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    registry_check: bool = False
    registry_max_age_days: int = Field(default=30, ge=0)
    registry_timeout_seconds: float = Field(default=3.0, gt=0)


class PromptInjectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class TestIntegrityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class LintSuppressionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class ErrorHandlingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class PublishCheckConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    ecosystem: Literal["auto", "npm", "python-sdist", "python-wheel"] = "auto"
    fail_on: Severity = Severity.HIGH


class ExplainConfig(BaseModel):
    """Controls the explanation adapter used by ``vibeguard explain``.

    ``adapter`` is a free-form string rather than a ``Literal`` because the
    set of valid names grows at runtime via the ``vibeguard.explain_adapters``
    entry-point group. Unknown names surface as a CLI error at command time,
    not at config-load time — the alternative would be to import every
    optional plugin before validating the config, which defeats the lazy
    discovery design.
    """

    model_config = ConfigDict(extra="forbid")

    adapter: str = Field(
        default="static",
        description=(
            "Name of the explanation adapter to use. The built-in 'static' "
            "adapter is always available; additional adapters can be "
            "contributed via the 'vibeguard.explain_adapters' entry point."
        ),
    )

    @model_validator(mode="after")
    def _adapter_not_empty(self) -> ExplainConfig:
        if not self.adapter or not self.adapter.strip():
            raise ValueError("'adapter' must be a non-empty string")
        # Normalize so a padded value like "static " matches the registry key
        # at lookup time (registry names are not stripped on lookup).
        self.adapter = self.adapter.strip()
        return self


class SeverityOverride(BaseModel):
    """A severity override for a specific rule or finding ID.

    `finding_id` is matched exactly against ``Finding.id`` (e.g. ``"SEC-ENV"``).
    To override a whole family of findings, scope by `rule_id` instead — every
    finding produced by that rule will be remapped. `finding_id` always wins
    over `rule_id` when both apply.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None
    finding_id: str | None = None
    severity: Severity

    @model_validator(mode="after")
    def _at_least_one_id(self) -> SeverityOverride:
        if not self.rule_id and not self.finding_id:
            raise ValueError("At least one of 'rule_id' or 'finding_id' must be provided")
        return self


class Suppression(BaseModel):
    """A policy suppression with required reason and optional expiry.

    `finding_id` is matched exactly against ``Finding.id`` (e.g. ``"SEC-ENV"``);
    `rule_id` matches every finding produced by that rule. When **both** are
    set on the same Suppression, the match is **OR**: a finding is suppressed
    if either identifier matches the configured `path_pattern`. Prefer scoping
    by `finding_id` alone for surgical suppressions and `rule_id` alone for
    family-wide ones — setting both is rarely what you want.
    """

    model_config = ConfigDict(extra="forbid")

    finding_id: str | None = None
    rule_id: str | None = None
    path_pattern: str = "**"
    reason: str
    expires: str | None = None

    @model_validator(mode="after")
    def _at_least_one_id(self) -> Suppression:
        if not self.rule_id and not self.finding_id:
            raise ValueError("At least one of 'rule_id' or 'finding_id' must be provided")
        return self

    @model_validator(mode="after")
    def _reason_not_empty(self) -> Suppression:
        if not self.reason.strip():
            raise ValueError("'reason' must not be empty")
        return self

    @model_validator(mode="after")
    def _expires_is_iso_date(self) -> Suppression:
        if self.expires is None:
            return self
        try:
            date.fromisoformat(self.expires)
        except ValueError as exc:
            raise ValueError(
                f"'expires' must be an ISO date (YYYY-MM-DD), got {self.expires!r}"
            ) from exc
        return self


class ScannerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_file_size_kb: int = Field(default=1024, ge=1)
    respect_gitignore: bool = Field(
        default=True,
        description=(
            "Honor the scan root's .gitignore during file collection (#211). "
            "Git-tracked files are always scanned even when gitignored, so a "
            "committed-but-usually-ignored file (e.g. a checked-in .env) still "
            "triggers findings. Set false to scan gitignored files too."
        ),
    )


class GitConfig(BaseModel):
    """Git/diff-mode settings.

    ``base_branch`` sets the ref that ``--diff`` compares against (``base...HEAD``)
    instead of the automatic ``origin/main`` → ``origin/master`` → ``main`` →
    ``master`` detection. The ``--base`` CLI flag overrides this value. Useful for
    teams whose default branch is ``develop``/``trunk`` or for stacked-PR bases;
    in GitHub Actions, pass ``--base "origin/${{ github.base_ref }}"``.
    """

    model_config = ConfigDict(extra="forbid")

    base_branch: str | None = None


class GateConfig(BaseModel):
    """Settings specific to the ``gate`` command (#218).

    ``strict_errors`` makes ``gate`` fail closed (non-zero exit) when the scan
    itself ran *degraded* — a rule crashed, a plugin failed to load, the git
    context was unavailable in ``--diff`` mode, an opt-in registry lookup failed,
    or a file could not be read. Routine skips (binary/oversize files) never trip
    it. Off by default so the gate stays fail-open on degradation unless a team
    opts in; the ``--strict-errors`` CLI flag overrides this value either way.
    Recommended for security-sensitive repositories where a partially-broken
    scan must not show a green check.
    """

    model_config = ConfigDict(extra="forbid")

    strict_errors: bool = False


class OutputConfig(BaseModel):
    """Report-output settings shared by scan/gate/publish-check.

    ``sarif_max_results`` caps the number of results in a single SARIF run so a
    large scan stays under GitHub Code Scanning's documented per-run ingestion
    limit (5,000). When exceeded, the SARIF reporter keeps the most severe
    findings and records the overflow in a ``toolExecutionNotifications`` entry
    (#227). Result sets at or below the cap are unaffected.
    """

    model_config = ConfigDict(extra="forbid")

    sarif_max_results: int = Field(default=5000, ge=1)


class PluginsConfig(BaseModel):
    """Controls third-party rule plugin discovery.

    Plugins are picked up via the ``vibeguard.rules`` entry-point group at
    scanner startup. Use ``disabled`` to opt a plugin out by its entry-point
    name (the left-hand side in ``my-rule = "pkg:Class"``) without uninstalling
    the source package — useful when a plugin is noisy on a particular repo
    but desirable elsewhere.
    """

    model_config = ConfigDict(extra="forbid")

    disabled: list[str] = Field(default_factory=list)


class VibeGuardConfig(BaseModel):
    """Root configuration model."""

    model_config = ConfigDict(extra="forbid")

    policy: Literal["relaxed", "balanced", "strict"] = "balanced"
    policy_pack: PolicyPackName | None = Field(
        default=None,
        description=(
            "Optional built-in policy pack name. When set, the pack's settings "
            "are merged in as defaults — every key the user has explicitly "
            "configured wins over the pack. See docs/policy-packs.md."
        ),
    )
    fail_on: Severity = Severity.HIGH
    baseline: str | None = Field(default=None, description="Path to baseline file")
    severity_overrides: list[SeverityOverride] = Field(default_factory=list)
    suppressions: list[Suppression] = Field(default_factory=list)
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
    slopsquat: SlopsquatConfig = Field(default_factory=SlopsquatConfig)
    prompt_injection: PromptInjectionConfig = Field(default_factory=PromptInjectionConfig)
    test_integrity: TestIntegrityConfig = Field(default_factory=TestIntegrityConfig)
    lint_suppressions: LintSuppressionsConfig = Field(default_factory=LintSuppressionsConfig)
    error_handling: ErrorHandlingConfig = Field(default_factory=ErrorHandlingConfig)
    publish_check: PublishCheckConfig = Field(default_factory=PublishCheckConfig)
    explain: ExplainConfig = Field(default_factory=ExplainConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    gate: GateConfig = Field(default_factory=GateConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)

    @classmethod
    def load(
        cls,
        path: Path | str | None = None,
        *,
        policy_pack: str | None = None,
    ) -> VibeGuardConfig:
        """Load config from a YAML file, falling back to defaults.

        If ``policy_pack`` is passed (typically from the CLI ``--policy-pack``
        flag), it takes precedence over any ``policy_pack:`` key inside the
        YAML file. The pack's settings are merged in as **defaults** — every
        key the user has explicitly set in their YAML still wins.

        Raises ``pydantic.ValidationError`` for invalid YAML, unknown pack
        names, or extra/unknown keys.
        """
        if path is None:
            path = Path("vibeguard.yaml")

        config_path = Path(path)
        if config_path.exists():
            # Read as UTF-8 explicitly (#167): the platform default is cp1252 on
            # Windows, which raises UnicodeDecodeError on the UTF-8 config files
            # VibeGuard writes and on arbitrary non-ASCII bytes.
            with config_path.open(encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
        else:
            data = {}

        if not isinstance(data, dict):
            # A non-mapping YAML root (scalar, list, …) is not a valid config.
            # Raise a clean TypeError instead of letting the .get()/** access
            # below fail with AttributeError — callers and the fuzz suite treat
            # TypeError as a recognised "malformed config" failure mode.
            raise TypeError(f"config root must be a YAML mapping, got {type(data).__name__}")

        effective_pack = policy_pack or data.get("policy_pack")
        if effective_pack and effective_pack in KNOWN_PACK_NAMES:
            # Known pack — merge its defaults in. We deliberately do NOT
            # short-circuit on unknown packs here: leaving the bad name in
            # ``data`` lets Pydantic's Literal check on ``policy_pack`` raise
            # a clean ValidationError with the valid options enumerated,
            # which is the contract callers expect.
            pack_data = load_policy_pack(effective_pack)
            pack_data.pop("policy_pack", None)
            data = merge_policy_pack(data, pack_data)
            # Round-trip the chosen pack onto the loaded model so callers can
            # introspect it (e.g. ``vibeguard validate`` echoes it back).
            data["policy_pack"] = effective_pack
        elif effective_pack and policy_pack:
            # Explicit kwarg with an unknown name — write it into the data
            # dict so Pydantic surfaces the Literal-mismatch error against
            # the user-visible key.
            data["policy_pack"] = policy_pack

        return cls.model_validate(data)

    def is_path_ignored(self, path: str | Path) -> bool:
        """Return True if ``path`` matches an ``ignore.paths`` pattern.

        Patterns use gitignore syntax (compiled via ``pathspec``), the same
        language as ``.vibeguardignore`` and ``.gitignore`` (#216). This
        replaced an earlier per-component ``fnmatch`` that could never match a
        multi-segment pattern such as ``packages/*/build/``. For the common
        directory-name case (``node_modules/``, ``__pycache__/``) the result is
        unchanged.
        """
        path_str = str(path).replace("\\", "/")
        return compile_pathspec(tuple(self.ignore.paths)).match_file(path_str)


def _read_ignore_lines(file_path: Path) -> list[str]:
    r"""Return non-blank, non-comment lines from an ignore file, verbatim.

    Shared by :func:`load_ignorefile` and :func:`load_gitignore`. Patterns are
    passed through unchanged so ``pathspec`` can apply gitignore's own rules
    (trailing whitespace is insignificant unless escaped with ``\``; ``\``
    escapes). Only blank/whitespace-only lines are dropped, and a line counts as
    a comment only when ``#`` is its first character — git does not treat an
    indented ``#`` as a comment, and stripping each line first (as an earlier
    version did) silently changed those edge cases.
    """
    if not file_path.exists():
        return []
    return [
        line
        for line in file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def load_ignorefile(root: Path) -> list[str]:
    """Load ``.vibeguardignore`` patterns from the scan root (gitignore syntax)."""
    return _read_ignore_lines(root / ".vibeguardignore")


def load_gitignore(root: Path) -> list[str]:
    """Load the scan root's ``.gitignore`` patterns (#211).

    Only the scan-root ``.gitignore`` is read in v1; nested ``.gitignore`` files
    deeper in the tree are deferred. Git-tracked files are re-included by the
    collector's carve-out regardless of these patterns, so a committed file that
    is also gitignored is still scanned.
    """
    return _read_ignore_lines(root / ".gitignore")


DEFAULT_CONFIG_YAML = """\
# VibeGuard configuration
# https://github.com/dgenio/vibeguard

# Optional: apply a built-in policy pack as defaults. User keys below
# always override the pack. See docs/policy-packs.md.
# policy_pack: web-app  # oss-library | web-app | strict-ci

policy: balanced      # relaxed | balanced | strict
fail_on: high         # info | low | medium | high | critical

# gate:
#   # Fail the gate when the scan itself ran degraded (a rule crashed, a plugin
#   # failed to load, git context was unavailable in --diff mode, a registry
#   # lookup failed, or a file was unreadable). Routine binary/oversize skips
#   # never trip it. Off by default; --strict-errors overrides this. Recommended
#   # for security-sensitive repos. See docs/stability-contract.md.
#   strict_errors: false

ignore:
  # gitignore-style patterns (same syntax as .vibeguardignore and .gitignore).
  # Multi-segment patterns like packages/*/build/ are supported.
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
  # Honor the scan root's .gitignore (git-tracked files are always scanned).
  # Set false to also scan gitignored files. config ignore.paths +
  # .vibeguardignore are the hard-ignore layer applied first; .gitignore only
  # excludes additional *untracked* files and cannot re-include a hard-ignored
  # path.
  respect_gitignore: true

# git:
#   # Base ref for --diff comparisons (base...HEAD). Overrides the default
#   # origin/main -> origin/master -> main -> master detection. The --base
#   # CLI flag wins over this value. In GitHub Actions, prefer passing
#   # --base "origin/${{ github.base_ref }}" on the command line.
#   base_branch: origin/develop

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
  # Source-test mapping for monorepos. Leave empty for standard
  # src/ ⇄ tests/ layouts. See docs/policy-packs.md#source-test-mapping
  # for the full semantics.
  # mapping:
  #   - source: "packages/api/src/**"
  #     tests:
  #       - "packages/api/tests/**"

ai_footprints:
  enabled: true

slopsquat:
  enabled: true
  # Opt-in network check: verify each dependency exists on the package
  # registry and is not suspiciously new. OFF by default — turning it on
  # makes scans perform network I/O and become non-deterministic.
  registry_check: false
  registry_max_age_days: 30
  registry_timeout_seconds: 3.0

prompt_injection:
  enabled: true

# Flags diffs that delete/skip tests or lower coverage thresholds — the
# "make CI green by disabling the check" failure mode.
test_integrity:
  enabled: true

# Flags newly introduced blanket linter/type-checker suppressions
# (bare `# noqa`, `# type: ignore`, `/* eslint-disable */`, `@ts-nocheck`,
# bare `#nosec`/`//nolint`). Scoped suppressions with codes are not flagged.
lint_suppressions:
  enabled: true

# Flags newly introduced swallowed errors (`except: pass`, empty `catch {}`,
# discarded Go errors). `contextlib.suppress(...)` is treated as explicit.
error_handling:
  enabled: true

publish_check:
  enabled: true
  ecosystem: auto     # auto | npm | python-sdist | python-wheel
  fail_on: high       # severity threshold when used as a gate

explain:
  # Adapter used by `vibeguard explain`. The default `static` adapter is
  # always available and never makes network calls. See
  # docs/explain-adapters.md for the contract and how to add custom adapters.
  adapter: static

# severity_overrides:
#   - rule_id: "AI-FOOTPRINT"
#     severity: high
#   - finding_id: "SEC-ENV"
#     severity: critical

# suppressions:
#   - finding_id: "SEC-ENV"
#     path_pattern: "tests/fixtures/**"
#     reason: "Test fixture — intentional example"
#     expires: "2026-12-31"

# baseline: .vibeguard-baseline.json
"""


def render_config_body(policy_pack: str | None) -> str:
    """Return the contents for a generated ``vibeguard.yaml``.

    With no pack, returns :data:`DEFAULT_CONFIG_YAML`. With a pack, returns a
    minimal file that defers to the pack (pack defaults apply at load time; user
    keys below the ``policy_pack`` line always win). The caller is responsible
    for validating that ``policy_pack`` names a real pack.

    Shared by ``vibeguard init`` and ``vibeguard setup github-actions`` so the
    two generators can never drift apart.
    """
    if policy_pack is None:
        return DEFAULT_CONFIG_YAML
    return (
        f"# VibeGuard configuration — generated from policy pack: {policy_pack}\n"
        "# Run `vibeguard init` to regenerate without a pack.\n"
        "#\n"
        "# Pack defaults are applied at load time; any value you set below\n"
        "# overrides the pack. See docs/policy-packs.md for the full list.\n\n"
        f"policy_pack: {policy_pack}\n"
    )


def apply_severity_overrides(
    findings: list[Finding], overrides: list[SeverityOverride]
) -> list[Finding]:
    """Apply severity overrides to findings, returning new Finding instances."""
    if not overrides:
        return findings

    result: list[Finding] = []
    for finding in findings:
        new_severity = finding.severity
        for override in overrides:
            if override.finding_id and finding.id == override.finding_id:
                new_severity = override.severity
                break
            if override.rule_id and finding.rule == override.rule_id:
                new_severity = override.severity
                # Don't break — a more specific finding_id override may follow
        if new_severity != finding.severity:
            result.append(finding.model_copy(update={"severity": new_severity}))
        else:
            result.append(finding)
    return result


def apply_policy_suppressions(
    findings: list[Finding], suppressions: list[Suppression]
) -> tuple[list[Finding], list[Finding]]:
    """Apply policy suppressions and return (active_findings, warning_findings).

    Expired suppressions emit a SUPPRESSION-EXPIRED warning instead of suppressing.
    """
    import fnmatch

    from vibeguard.models import Confidence, Finding, Severity

    if not suppressions:
        return findings, []

    active: list[Finding] = []
    warnings: list[Finding] = []

    # Pre-check for expired suppressions. `expires` is validated as an ISO
    # date at config load (see Suppression._expires_is_iso_date), so we can
    # parse it directly without a defensive try/except — a malformed value
    # would have failed at load time rather than silently never expiring.
    today = date.today()
    expired_suppressions: set[int] = set()
    for idx, supp in enumerate(suppressions):
        if supp.expires:
            expiry = date.fromisoformat(supp.expires)
            if expiry < today:
                expired_suppressions.add(idx)
                warnings.append(
                    Finding(
                        id="SUPPRESSION-EXPIRED",
                        rule="suppressions",
                        title="Policy suppression expired",
                        description=(
                            f"Suppression for {supp.finding_id or supp.rule_id} "
                            f"(path: {supp.path_pattern}) expired on {supp.expires}."
                        ),
                        severity=Severity.LOW,
                        path="vibeguard.yaml",
                        recommendation="Remove or renew the expired suppression.",
                        tags=["suppressions"],
                        confidence=Confidence.HIGH,
                    )
                )

    for finding in findings:
        suppressed = False
        for idx, supp in enumerate(suppressions):
            if idx in expired_suppressions:
                continue

            # Check if rule_id or finding_id matches
            id_match = False
            if (
                supp.finding_id
                and finding.id == supp.finding_id
                or supp.rule_id
                and finding.rule == supp.rule_id
            ):
                id_match = True

            if not id_match:
                continue

            # Check path pattern
            finding_path = finding.path.replace("\\", "/")
            if fnmatch.fnmatch(finding_path, supp.path_pattern):
                suppressed = True
                break

        if not suppressed:
            active.append(finding)

    return active, warnings


# Resolve the ``ScanContext.config: "VibeGuardConfig"`` forward reference now
# that ``VibeGuardConfig`` is defined (#217, #189). ``vibeguard.models`` cannot
# import this module at runtime — ``config`` imports ``Severity``/``ScanContext``
# from ``models`` — so the annotation is a string there and is bound here, the
# single place where both classes are in scope. Keep this the only rebuild site
# so the deferred-annotation wiring lives in one documented location.
ScanContext.model_rebuild()
