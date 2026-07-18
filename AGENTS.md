# AGENTS.md

Guidance for AI coding agents working **on the VibeGuard codebase** (most of its
PRs originate from agent branches). This encodes the project-specific contract
that otherwise gets rediscovered PR after PR. Human contributors: see
[CONTRIBUTING.md](CONTRIBUTING.md) — this file is the short, high-signal version
of the same rules.

> Scope: this is about contributing *to* VibeGuard. It is **not** about using
> VibeGuard inside your own agent workflow, and it is not a detection rule.

## Run the real gate before every push

```bash
make ci
```

`make ci` runs **seven** checks, and GitHub Actions enforces all of them:
`lint`, `format-check`, `typecheck`, `docs-check`, `bench-precision-check`,
`check-versions`, `test`. Running only `pytest` is the single most common cause
of a red PR — the drift guards (`docs-check`, `bench-precision-check`,
`check-versions`) and `mypy` are exactly what a partial run misses. There is a
`make pre-push` alias; wiring it as a git `pre-push` hook makes this automatic.

## Generated files — never hand-edit

Regenerate them and commit the result; a CI drift guard fails otherwise:

| File | Regenerator |
|---|---|
| `docs/rules.md` | `make docs` |
| `docs/precision-report.md` | `make bench-precision` |
| `tests/fixtures/golden/*` | `make update-goldens` |
| version references across docs | keep in sync; verify with `make check-versions` |

## Adding a rule: wire it into two import sites

A new rule must be registered in **both** places or it silently misbehaves:

1. `vibeguard/scanner.py` — add the class under the matching
   `if config.<name>.enabled:` block.
2. `vibeguard/rules/__init__.py:load_all_builtin_rules` — add the module so
   `RULE_REGISTRY` is populated for the CLI, doc generation, and plugin
   discovery paths that don't go through the scanner.

Scaffold the skeleton with `vibeguard dev new-rule <name> --finding-prefix <PREFIX>`
(add `--dry-run` to preview). Full walkthrough: `docs/how-to-add-a-rule.md`.

## Known traps

- **mypy runs in a ratcheting config** (`disallow_untyped_defs`,
  `no_implicit_optional`). Annotate every function; write `X | None` explicitly.
  Annotate `Literal` locals that mypy would otherwise widen. Don't reintroduce a
  global `ignore_missing_imports` — unstubbed imports are allow-listed per module
  in `pyproject.toml`.
- **Runtime dependencies are a budget** (`RUNTIME_DEPENDENCY_BUDGET` in
  `tests/test_packaging_floor.py`). Adding one fails CI until it's added to the
  allowlist and justified; heavier features go behind an optional extra.
- **GitHub Actions are SHA-pinned** with a version comment. Match that style in
  any workflow you touch, including the generated template in
  `vibeguard/ci_setup.py`.

## PR hygiene

- One focused issue per PR; small related maintenance items may be batched when
  genuinely cleaner (say so in the description).
- Put `Closes #NNN` in the PR body.
- Conventional-commit title (`feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`,
  `refactor:`).
- Keep your branch current with `git rebase origin/main` — not `git merge main`.
