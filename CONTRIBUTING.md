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

## Prerequisites

- **Python 3.10 or newer.** CI tests against 3.10, 3.11, and 3.12.
- **git** with a clone of the repository.
- Recommended: a fresh virtual environment (`python -m venv .venv && source .venv/bin/activate`)
  or a tool like [`pyenv`](https://github.com/pyenv/pyenv) /
  [`uv`](https://github.com/astral-sh/uv).

## Editable install

From the repo root:

```bash
pip install -e ".[dev]"
```

This installs VibeGuard in editable mode along with the dev tooling
(`pytest`, `pytest-cov`, `ruff`, `mypy`, `types-PyYAML`). The CLI is then
available as `vibeguard`.

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

`mypy` runs in non-strict mode (`tool.mypy.strict = false` in
`pyproject.toml`). Don't add `# type: ignore` to silence warnings unless
you genuinely cannot avoid them — usually a small refactor is cleaner.

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

If you're adding a brand-new detection rule, the high-level steps are:

1. Pick a stable `rule_id` (snake_case) and one or more `<PREFIX>-<NAME>`
   finding IDs that follow the existing convention.
2. Implement the rule under `vibeguard/rules/` as a subclass of
   `vibeguard.rules.base.Rule`.
3. Register a `RuleMetadata` entry via `register_rule(...)` at
   import time.
4. Wire the rule into `vibeguard/scanner.py` (the scanner imports each
   rule module explicitly today — there's no auto-discovery for built-ins).
5. Add tests under `tests/test_<rule>.py` mirroring an existing rule's
   test file (`test_secrets.py` and `test_packaging.py` are good models).
6. If the issue includes a triggering example, add it to
   `examples/vulnerable-node-package` or `examples/vulnerable-python-package`
   so `make demo` exercises the new rule.

The detailed walkthrough (with a worked example) lives in
[`docs/how-to-add-a-rule.md`](docs/how-to-add-a-rule.md). The steps above
plus an existing rule module (`vibeguard/rules/secrets.py` is a good
model) are enough to get a working rule.

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
