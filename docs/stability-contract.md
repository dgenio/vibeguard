# VibeGuard Stability Contract (v1)

VibeGuard is built to run as a **pre-merge gate in CI**. A gate is only
worth enforcing if its behaviour is predictable across releases. This page
is the contract: it states which surfaces are stable, how compatibility is
handled, and what counts as a breaking change.

Anything documented as **stable** here will not change in a backwards-
incompatible way without a major version bump and a migration note in the
release notes. Anything marked **experimental** may change in a minor
release.

> Scope: this contract covers the user-facing product surface (CLI,
> outputs, finding IDs, config). The *plugin* API has its own contract in
> [`plugin-api.md`](plugin-api.md), governed by `PLUGIN_API_VERSION`.

> Enforcement: the promises below are executable. A dedicated contract suite,
> [`tests/test_stability_contract.py`](../tests/test_stability_contract.py),
> pins the exit codes, the `scan`-vs-`gate` split, fail-closed behaviour,
> output-schema keys, finding-ID set, fingerprint algorithm, and output
> ordering — so the document and the binary cannot silently disagree. An
> *intentional* contract change must update the doc and that suite together.

> Security semantics for Trustworthy Observe are governed by the
> [normative threat model](threat-model.md). The stability contract must not be
> read as a stronger claim: a complete run or no findings is not proof that a
> change is secure.

---

## TL;DR

| Surface | Stability | Notes |
|---|---|---|
| `scan`, `gate`, `init`, `explain`, `rules`, `publish-check`, `baseline`, `version` commands | **Stable** | Names, exit-code meanings, and core flags |
| Exit codes (`0` / `1` / `2`) | **Stable** | See [Exit codes](#exit-codes) |
| Finding IDs (`SEC-ENV`, `MAP-DIST`, …) | **Stable** | Renames are breaking; deprecations are documented |
| Rule IDs / config section keys | **Stable** | The `rule id` ↔ `config_key` mapping is published in `rules.md` |
| JSON / SARIF / diagnostics output schemas | **Stable** | Documented in [`output-schemas.md`](output-schemas.md) |
| Console (Rich) table layout | **Experimental** | Human-facing; may be re-laid-out without a major bump |
| Markdown / PR-comment wording | **Experimental** | Structure is stable; exact prose is not |
| `vibeguard.yaml` schema | **Stable, additive** | New keys are additive; removing/repurposing a key is breaking |
| `dev`-namespaced / undocumented commands | **Experimental** | Not part of v1 |

---

## CLI command stability

These commands and their documented behaviour are stable for v1:

- `vibeguard init` — create a `vibeguard.yaml`. Never overwrites an existing
  config; exits `0` with a notice if one is present.
- `vibeguard scan` — **informational**. It prints findings and
  **always exits `0`** *on findings*, even with `--fail-on` — `--fail-on` on
  `scan` only sets the severity used to mark findings as "blocking" in the
  output; it does not turn findings into a non-zero exit. Operational errors
  (a bad `--path`, malformed config) are the exception: like every command,
  `scan` still **fails closed with exit `2`** when it cannot run — see
  [Exit codes](#exit-codes).
- `vibeguard gate` — runs the same analysis as `scan` but **exits `1`** when
  findings meet or exceed the `--fail-on` threshold.
- `vibeguard explain <ID>` — remediation for a finding ID.
- `vibeguard rules list` / `vibeguard rules explain <rule-id>` — rule
  discovery.
- `vibeguard publish-check` — gate on the *published* file set for npm /
  python sdist.
- `vibeguard baseline create|update` — manage accepted-findings baselines.
- `vibeguard version` — version / Python / platform / install path.

The `scan` vs `gate` distinction is the most important contract in this
file: **`scan` never fails your build on findings; `gate` is the thing you
put in CI.** (Both still exit `2` on an operational error such as a bad path
— "informational" means "findings don't fail the build", not "scan can never
exit non-zero".) This split is guaranteed by tests (`tests/test_cli.py`,
`tests/test_cli_e2e.py::TestScanFailOnHelp`, `::TestPathValidation`).

## Exit codes

| Code | Meaning | Applies to |
|---|---|---|
| `0` | Success — analysis completed with no blocking findings (`scan` returns `0` for *any* completed analysis, regardless of findings) | all commands |
| `1` | Blocking findings at or above `--fail-on` | `gate`, `publish-check` |
| `2` | Operational/usage error (bad path, malformed config, unknown ID) — **every** command fails closed here, including `scan` | all commands |

Exit `2` is reserved for "the tool could not run as asked". It is distinct
from `1` ("the tool ran and the gate failed") so CI can tell a real failure
from a misconfiguration.

These codes are exposed in the CLI as the named constants `EXIT_OK`,
`EXIT_BLOCKED`, and `EXIT_USAGE` so the contract lives in one place rather than
scattered integer literals (#183). `validate` additionally uses exit `1` to
report that a config file is invalid.

**Fail-closed on a degraded scan (opt-in).** `gate --strict-errors` (or
`gate.strict_errors: true`) makes `gate` exit `1` when the scan itself ran
degraded — a rule crashed, a plugin failed to load, git context was unavailable
in `--diff` mode, an opt-in registry lookup failed, or a file was unreadable —
even with zero blocking findings (#218). Routine binary/oversize skips never
trip it. It is **off by default**, so existing pipelines are unaffected;
security-sensitive repositories are encouraged to enable it.

## Config file compatibility

- The `vibeguard.yaml` schema is **stable and additive**: new optional keys
  may appear in minor releases with safe defaults.
- Removing a key, renaming a key, or changing a default in a way that makes
  a previously-clean repo fail is a **breaking change** and requires a major
  bump.
- The `rule id` ↔ `config_key` mapping is not always 1:1 (for example, the
  `risky_diff` rule is configured under `risky_patterns:`). The authoritative
  mapping is published per-rule in [`rules.md`](rules.md) and via
  `vibeguard rules explain <rule-id>`.
- A missing config file is **not** an error — VibeGuard loads built-in
  defaults (`tests/test_config.py::test_load_nonexistent_returns_defaults`).
- A malformed or invalid config (bad `fail_on`, unknown `policy`, etc.)
  **fails closed** with exit `2` rather than silently falling back
  (`tests/test_config.py`).

### Ignore semantics and scan scope

- **One pattern grammar.** `ignore.paths`, `.vibeguardignore`, and `.gitignore`
  all use gitignore syntax (via `pathspec`). Multi-segment patterns such as
  `packages/*/build/` work everywhere; bare directory names (`node_modules/`)
  match at any depth (#216).
- **Two ignore layers.** The *hard-ignore* layer merges `ignore.paths` and
  `.vibeguardignore` into one ordered gitignore spec; within it later patterns
  win, so a `!` negation in `.vibeguardignore` can re-include a path
  `ignore.paths` matched. Paths it matches are always skipped, and ignored
  directories are pruned — so, as with git, a `!` negation cannot re-include a
  path whose parent directory the hard-ignore layer excluded, because that
  directory is pruned during the walk and never descended. `.gitignore` is a
  separate layer, applied only when
  `respect_gitignore` is on: it can exclude additional **untracked** files but
  cannot re-include a path the hard-ignore layer already excluded, and never
  excludes a git-tracked file.
- **`.gitignore` is honored by default** (`scanner.respect_gitignore: true`,
  #211). Gitignored, *untracked* files are skipped; **git-tracked files are
  always scanned**, so a committed-but-usually-ignored file (e.g. a checked-in
  `.env`) still triggers `SEC-ENV`. This is a behavior change from earlier
  releases — set `scanner.respect_gitignore: false` to restore scanning of
  gitignored files. When `git` is unavailable the scan-root `.gitignore` is
  still applied as a plain pattern file, without the tracked-file carve-out.
- Scanning is otherwise unchanged: only regular, non-binary, size-limited files
  are collected, and output ordering stays sorted
  (`tests/test_file_collection.py`).

## Finding ID and rule metadata stability

- **Finding IDs are stable identifiers.** Once a finding ID ships in a
  release it will not be renamed or repurposed without a major bump. If a
  finding is retired, its ID is documented as deprecated rather than reused.
- This is what makes `ignore.findings`, `severity_overrides`, and SARIF
  `ruleId` correlation safe to pin in your own config.
- **Default severities are stable**, but are user-overridable via
  `severity_overrides` and policy packs. Raising a default severity (which
  can newly-block a previously-passing gate) is treated as a breaking change
  for the affected finding and called out in release notes.
- Rule metadata (`rule_id`, `config_key`, `default_severity`, `confidence`,
  `finding_ids`) is published in [`rules.md`](rules.md), regenerated from the
  registry by `make docs`.

## Output schema stability

The machine-readable reporters are integration surfaces and are stable:

- **JSON** (`--json`), **SARIF** (`--sarif`), and **IDE diagnostics** field
  shapes are documented in [`output-schemas.md`](output-schemas.md) and
  guarded by golden snapshot tests (`tests/test_reporters_golden.py`,
  `tests/test_sarif.py`). New fields may be added; existing fields are not
  removed or retyped without a major bump.
- The **console (Rich) table** and **Markdown / PR-comment** renderers are
  human-facing. Their *structure* (a severity-sorted table; a PASS/FAIL
  headline that reflects blocking findings) is stable, but exact column
  widths and prose are **experimental** and may change in a minor release.
  Do not parse the console output — use `--json`/`--sarif`.

### Output ordering

Findings are emitted in a **canonical, deterministic order: sorted by
`(path, line, id)`** — file path first, then line number (file-level findings,
which have no line, sort before line-scoped findings in the same file), then
finding ID as the final tie-break. This order is applied once to the scan
result, so it is a property of the result itself and is identical across the
machine-readable reporters that preserve result order (JSON, RDJSON, SARIF,
Sonar, IDE diagnostics) and stable across repeated runs and platforms. The
human-facing console and Markdown renderers re-group by severity on top of this
order for readability; that presentation ordering is **experimental** as noted
above. Two consecutive scans of the same tree produce byte-identical JSON —
downstream consumers that diff VibeGuard output (PR comments, baselines, golden
files) can rely on it. Guaranteed by `tests/test_stability_contract.py`.

## Offline guarantee

The core gate performs **no network I/O**: `scan`, `gate`, `publish-check`,
and `explain` run entirely offline — no telemetry, no API key, no LLM in the
loop. This is the product thesis (air-gapped CI, supply-chain reviewability,
deterministic behaviour), not a best-effort default.

The one sanctioned exception is **opt-in**: the `slopsquat` rule's registry
check (`slopsquat.registry_check: true`, off by default) makes network calls to
verify a dependency exists and is not suspiciously new. With it off — the
default — the gate never touches the network.

The guarantee is mechanically enforced, not just documented:

- The test suite runs with sockets disabled (`--disable-socket` via
  `pytest-socket`), so any test that opens a network connection fails. A test
  that legitimately needs a socket must opt in with `@pytest.mark.enable_socket`.
- A CI job (`offline-guarantee` in `.github/workflows/ci.yml`) runs the four
  core commands as subprocesses inside a network namespace with no
  connectivity and asserts none fail with an operational error.

## Plugin API stability

The plugin API is versioned independently via `PLUGIN_API_VERSION`
(currently `1.0`) and documented in [`plugin-api.md`](plugin-api.md).
Plugins import only from `vibeguard.api`; everything else under
`vibeguard.*` is internal and may change without notice.

## Versioning policy

VibeGuard follows semantic versioning for the surfaces above:

- **MAJOR** — a backwards-incompatible change to any *stable* surface
  (removed/renamed command, removed finding ID, removed/retyped output
  field, removed/renamed config key, raised default severity that can
  newly-block).
- **MINOR** — additive, backwards-compatible changes (new rule, new finding
  ID, new optional config key, new output field, new command).
- **PATCH** — bug fixes and detection-accuracy improvements that do not
  change the stable contract.

Detection improvements are a deliberate grey area: fixing a false negative
can newly-block a repo even in a patch release. We bias toward shipping these
in **minor** releases and calling them out in the release notes when they can
realistically change a gate result. The [release checklist](release-checklist.md)
codifies this.

## Operational behaviour ("fails closed")

A safety gate must never report success when it could not actually do its
job. The following operational cases are guaranteed and test-backed:

| Case | Behaviour | Guaranteed by |
|---|---|---|
| A scan target does not exist | exit `2`, error message, **never** "Gate passed" | `tests/test_cli_e2e.py::TestPathValidation` (#81) |
| A file is named as a scan target | scanned directly (never silently 0 files); `--diff`/`--staged` still require a directory (exit `2`) | `tests/test_cli_e2e.py::TestPathValidation` (#83, #213) |
| Malformed / invalid config | exit `2`, fail closed | `tests/test_config.py` |
| Zero files scanned due to user error | surfaced, not silently "clean" | `tests/test_cli_e2e.py` (#83) |
| `scan --pr-comment` with blocking findings | headline is **FAIL**, not PASS | `tests/test_pr_comment.py` (#82) |
| `explain` / `rules explain` unknown ID | exit `2`, consistent message | `tests/test_cli.py`, `tests/test_cli_e2e.py` (#90) |
| Plugin fails to load | scan continues; failure is reported as a `plugin_load` diagnostic, not swallowed | `tests/test_plugin_discovery.py` |
| `git` unavailable in `--diff` mode | reported as a `git_context` diagnostic; does not crash the gate | diff-scope handling |
| Degraded scan under `gate --strict-errors` | exit `1` even with zero findings; routine binary/oversize skips do **not** trip it | `tests/test_scan_diagnostics.py::TestGateStrictErrors` (#218) |
| Malformed config under `scan`/`gate` | exit `2`, error message names the underlying cause | `tests/test_cli_e2e.py::TestMalformedConfigErrorContext` (#183) |
| Base branch undetectable in `--diff` mode | scan degrades to `git diff HEAD` **and emits a diagnostic** (shallow clones get a `fetch-depth: 0` hint) — never a silent narrowing | `tests/test_diff_scope.py::TestDegradedGitDiagnostic` (#182) |
| Unverifiable explicit `--base` / `git.base_branch` | warning recorded, falls back to detection — not silently ignored | `tests/test_git.py` (#208) |

## Diff-mode scope semantics (`--diff`)

`--diff` answers "what did *this change* introduce or touch", so its scope is
the change set, not the whole repository:

- A finding is reported only if its file is part of the diff. Findings
  attributable to files **outside** the diff (pre-existing repository state) are
  not reported, so a PR gate is never blocked by unrelated history.
- Line-level findings are kept only when they fall on **added/changed lines**;
  file-level findings on a changed file are kept.
- If a changed file produces no parseable line ranges (rename, binary,
  mode-only, parse gap), its findings are kept **conservatively** — scoping
  never loses signal.
- Diff-aggregate findings (`DIFF-SIZE`, `DIFF-BREADTH`, `DIFF-RISK-FILES`) are
  always reported in diff mode.

The base ref is resolved as `--base` → `git.base_branch` config → automatic
detection (`origin/main` → `origin/master` → `main` → `master`). The diff text
contract is pinned (`color.diff=never`, `core.quotePath=false`, `--no-ext-diff`,
explicit `a/`/`b/` prefixes) so local git configuration cannot change scoping.

`--staged` (the staged index, `git diff --cached`) and `--patch` (a unified diff
scanned standalone, before it is applied) apply the same change-set filtering as
`--diff`. The three are mutually exclusive. See
[scan-scope.md](scan-scope.md) for the full scan-scope reference — targets,
modes, and precedence.

## What is *not* covered by this contract

- Exact console colours, icons, and table column widths.
- Exact wording of human-facing messages and Markdown prose.
- Internal module layout under `vibeguard.*` (use `vibeguard.api` for
  plugins).
- Benchmark numbers (informational; see [`benchmark.md`](benchmark.md)).
- Anything explicitly marked experimental above.

## Reporting a contract break

If a release changes any **stable** surface above without a major bump and a
migration note, that is a bug — please
[open an issue](https://github.com/dgenio/vibeguard/issues/new/choose) and
reference this contract.
