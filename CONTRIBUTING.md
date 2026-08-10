# Contributing to VibeGuard

Thanks for your interest in contributing. VibeGuard is a deterministic
pre-merge safety gate for AI-generated code — its value depends on being
fast, predictable, and trustworthy, so the contribution bar is "small,
focused, and well-tested" over "big and clever."

This guide covers the basics. For deeper rule-authoring guidance, see
[`docs/how-to-add-a-rule.md`](docs/how-to-add-a-rule.md) (once available).
For security disclosures, see [SECURITY.md](SECURITY.md) — do not file
public issues for vulnerabilities.

---

## Project direction & where to start

VibeGuard's current focus is **trust before breadth** — hardening and
documenting the gate before adding many new rules. Before picking up a
larger change, skim:

- **[docs/roadmap.md](docs/roadmap.md)** — Now / Next / Later / Non-goals,
  the issue **label taxonomy** (`good-first-issue`, `v1-blocker`,
  `rule-request`, …), what makes a good rule, and when to ship a plugin
  instead of a core rule.
- **[docs/stability-contract.md](docs/stability-contract.md)** — the
  promises core rules and outputs carry, so you know what counts as a
  breaking change.

Good first contributions: issues labelled `good-first-issue`,
false-positive reports with a clear repro, and docs. New rules and
integrations land most easily when they match the **Now / Next** focus in
the roadmap. Maintainers cutting a release should follow
[docs/release-checklist.md](docs/release-checklist.md).

---

## Prerequisites

- **Python 3.10 or newer.** CI tests the full matrix 3.10 → 3.14, plus a
  floor-deps job that resolves the minimum declared direct dependency versions
  from `pyproject.toml` with uv `lowest-direct` on 3.10.
- **pip 25.1 or newer** for local PEP 735 dependency-group installation. The
  command below upgrades pip before using `--group`.
- **git** with a clone of the repository.
- Recommended: a fresh virtual environment (`python -m venv .venv && source .venv/bin/activate`)
  or a tool like [`pyenv`](https://github.com/pyenv/pyenv) /
  [`uv`](https://github.com/astral-sh/uv).

## Editable install

From the repo root:

```bash
python -m pip install --upgrade pip
python -m pip install -e . --group dev
```

This installs VibeGuard in editable mode plus the local PEP 735 `dev`
dependency group (`pytest`, `pytest-cov`, `ruff`, `mypy`, `types-PyYAML`,
etc.). The group is contributor/CI tooling only and is **not published as an
optional dependency of the VibeGuard wheel**. The CLI is then available as
`vibeguard`.

Verify the install:

```bash
vibeguard --version
vibeguard --help
```

---

## Running the test suite

```bash
pytest                      # all tests, verbose by default
pytest --tb=short           # shorter traceback on failure
pytest -k missing_tests     # subset matching a keyword
pytest tests/test_cli.py -v # one file
```

Coverage report (matches CI):

```bash
make test
```

This runs `pytest tests/ -v --cov=vibeguard --cov-report=term-missing --cov-report=xml`.

**Coverage ratchet.** Branch coverage is enforced with a floor
(`fail_under` in `pyproject.toml`, under `[tool.coverage.report]`), so a change
that drops coverage below the floor fails CI. The floor is a **ratchet — it
only moves up**: a PR that meaningfully raises coverage may bump the number,
but no PR may lower it. Check your effect locally with
`pytest --cov=vibeguard` before pushing; if you're adding code, add the tests
that cover it in the same PR.

## Linting and formatting

VibeGuard uses [`ruff`](https://docs.astral.sh/ruff/) for both linting and
formatting. There is no separate `black` step.

```bash
ruff check vibeguard/ tests/      # lint
ruff format vibeguard/ tests/     # auto-format
ruff format --check vibeguard/ tests/   # CI's format check
```

The Makefile wraps these as `make lint` and `make format-check`.

## Type checking (optional but encouraged)

```bash
mypy vibeguard/
```

`mypy` runs in a **ratcheting** configuration (`pyproject.toml`): not full
`strict` yet, but `disallow_untyped_defs` and `no_implicit_optional` are on,
so **new code in `vibeguard/` must be annotated** — every function needs
argument and return types, and an optional parameter must say `X | None`
explicitly rather than relying on an implicit default. Unstubbed third-party
imports are allow-listed per-module (see `[[tool.mypy.overrides]]`); do not
re-introduce a global `ignore_missing_imports`. The strictness only tightens
over time — new flags are added in waves, never relaxed. Don't add
`# type: ignore` to silence warnings unless you genuinely cannot avoid them,
and add a comment when you must — usually a small refactor is cleaner.

## Full CI pipeline locally

```bash
make ci
```

That runs, in order: `lint`, `format-check`, `typecheck`, `test`. If
`make ci` is green locally, GitHub Actions almost always is too.

---

## Running VibeGuard against the bundled examples

```bash
vibeguard scan --path examples/vulnerable-node-package
vibeguard scan --path examples/vulnerable-python-package
```

Both example directories deliberately ship with realistic-looking risky
code (fake secrets, source-map leaks, AI footprints) so the scanner has
something meaningful to report. Use them to sanity-check rule changes.

`make demo` runs both scans in one go.

## Running VibeGuard against itself

This is the same gate CI runs on every PR:

```bash
vibeguard gate --path . --fail-on critical
```

If you add a new rule or change a finding's severity, run this before
pushing. The repo's own `vibeguard.yaml` and ignore paths are tuned so
the self-scan stays clean.

---

## Branch naming

We follow simple prefixes — make the prefix match the kind of change:

| Prefix      | Use for                                          |
|-------------|--------------------------------------------------|
| `feat/`     | New features, new rules, new CLI commands        |
| `fix/`      | Bug fixes, false-positive corrections            |
| `docs/`     | README, CONTRIBUTING, `docs/`, docstrings        |
| `test/`     | Adding or strengthening tests, no behavior change|
| `refactor/` | Code reorganization with no behavior change      |
| `chore/`    | Tooling, deps, CI, version bumps                 |
| `ci/`       | GitHub Actions / workflow changes                |

Examples: `feat/policy-packs-oss-library`, `fix/secrets-bearer-false-positive`,
`docs/contributing-guide`.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/). The
prefix matches the branch prefix above (`feat:`, `fix:`, `docs:`, etc.).
Keep the subject under ~72 characters; put the "why" in the body.

```
feat(rules): add PKG-COVERAGE-LEAK for committed coverage directories

Detects coverage/, htmlcov/, .nyc_output/, lcov-report/ in package roots
that are not excluded by .npmignore / MANIFEST.in. Mirrors the existing
PKG-NPMLEAK detection style.
```

## Pull request guidance

**Keep PRs focused.** One issue, one PR. If you spot something adjacent
that needs fixing, file a follow-up issue — don't bundle it.

**Link the issue.** Use `Closes #NNN` in the PR body so it auto-closes on
merge. The PR template prompts for this.

**Match the repo's idioms.** Before adding a new pattern, grep for an
existing example and match its style (test layout, error handling,
naming). VibeGuard's review culture is "match what's there" over
"introduce a better way."

**Avoid mixing refactors with behavior changes.** If a refactor makes the
diff hard to read, do it in a separate PR first.

**Use draft PRs.** If you want early feedback before the work is finished,
open the PR as a draft and ask in the description.

---

## Adding a new rule

If you're adding a brand-new detection rule, scaffold the skeleton first:

```bash
vibeguard dev new-rule exposed_supabase_key --finding-prefix SEC-SUPABASE
```

This generates the rule module and a matching test from the repo's
conventions (add `--dry-run` to preview, `--draft` to keep CI green while it's
a stub, `--force` to overwrite). It then prints the manual steps below — the
ones that need human judgement and are not auto-wired.

The high-level steps are:

1. Pick a stable `rule_id` (snake_case) and one or more `<PREFIX>-<NAME>`
   finding IDs that follow the existing convention.
2. Implement the rule under `vibeguard/rules/` as a subclass of
   `vibeguard.rules.base.Rule`.
3. Register a `RuleMetadata` entry via `register_rule(...)` at
   import time.
4. Wire the rule into both import sites: add the class to
   `vibeguard/scanner.py` (with an `if config.<name>.enabled:
   rules.append(...)` block matching the surrounding rules) **and** add
   the module to `vibeguard/rules/__init__.py:load_all_builtin_rules`
   so `RULE_REGISTRY` is populated for any code path that uses the
   registry without going through the scanner (CLI `rules list`/`explain`,
   doc generation, plugin discovery).
5. Add tests under `tests/test_<rule>.py` mirroring an existing rule's
   test file (`test_secrets.py` and `test_packaging.py` are good models).
6. If the issue includes a triggering example, add it to
   `examples/vulnerable-node-package` or `examples/vulnerable-python-package`
   so `make demo` exercises the new rule.

The full worked example lives in
[`docs/how-to-add-a-rule.md`](docs/how-to-add-a-rule.md). Start there
when implementing a new rule; the high-level steps above are a quick
reference for reviewers and contributors who already know the layout.

---

## Reporting issues

We use GitHub issue forms — pick the one that fits:

- **Bug report** — incorrect behavior, crash, unexpected output.
- **Feature request** — new CLI commands, reporters, integrations.
- **Rule request** — a new pattern to detect.
- **False-positive report** — an existing rule firing on benign code.

For **security vulnerabilities**, use the
[private advisory link](https://github.com/dgenio/vibeguard/security/advisories/new)
instead — see [SECURITY.md](SECURITY.md) for what's in scope.

---

## License

By contributing, you agree that your contributions will be licensed under
the [Apache License 2.0](LICENSE), the same license as the rest of the
project.
