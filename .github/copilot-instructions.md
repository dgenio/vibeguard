# Copilot instructions for VibeGuard

Repo context for the bot reviewer so it produces fewer repetitive findings. The
full contract is in [AGENTS.md](../AGENTS.md); the essentials:

- **The gate is `make ci`** (seven checks: lint, format-check, typecheck,
  docs-check, bench-precision-check, check-versions, test). A PR that only ran
  `pytest` has not been verified. Flag missing `mypy` / drift-guard coverage.
- **Generated files are never hand-edited:** `docs/rules.md` (`make docs`),
  `docs/precision-report.md` (`make bench-precision`), golden snapshots
  (`make update-goldens`). A hand-edit to these is a defect.
- **A new rule must be wired into two import sites** — `vibeguard/scanner.py`
  *and* `vibeguard/rules/__init__.py:load_all_builtin_rules`. Missing the second
  is a recurring bug.
- **mypy is ratcheting:** every function annotated; `X | None` explicit;
  `Literal` locals annotated. No global `ignore_missing_imports`.
- **Runtime dependencies are budgeted** (`RUNTIME_DEPENDENCY_BUDGET` in
  `tests/test_packaging_floor.py`); a new one needs the allowlist updated in the
  same PR.
- **GitHub Actions are SHA-pinned** with a `# vX.Y.Z` comment, including the
  template in `vibeguard/ci_setup.py`.
- **Finding paths are `/`-separated on every OS;** don't suggest `os.path.join`
  or `str(path)` in finding output — use `Path.as_posix()`.
