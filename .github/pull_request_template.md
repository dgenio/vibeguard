<!--
Thanks for contributing to VibeGuard! Please fill in the sections below.
Delete any sections that genuinely do not apply, but do not delete the checklist.
-->

## Linked issue

Closes #

## Summary of changes

<!-- One short paragraph: what changed and why. -->

## Type of change

<!-- Tick all that apply. -->

- [ ] Bug fix
- [ ] New feature
- [ ] New or updated detection rule
- [ ] Documentation
- [ ] Refactor (no behavior change)
- [ ] Tests
- [ ] CI / build / packaging

## How verified

<!-- Exact commands you ran, and a one-line result for each. -->

- `pytest` — _N passed_
- `ruff check vibeguard/ tests/` — _no issues_
- `ruff format --check vibeguard/ tests/` — _no diffs_
- `mypy vibeguard/` — _no errors_
- `vibeguard gate --path . --fail-on critical` — _exit 0_
- Manual testing steps (if any):

## Docs impact

<!-- Did README, docs/, or CONTRIBUTING change? If a new rule, is docs/rules.md regenerated? -->

- [ ] No docs change needed
- [ ] README / docs updated
- [ ] `docs/rules.md` regenerated (`make docs` or `scripts/generate_rule_docs.py`)
- [ ] N/A — explain:

## Scope / risk

<!--
Anything reviewers should pay particular attention to: backward-incompatible
changes, new dependencies, performance considerations, security-sensitive
code paths.
-->

- [ ] Any new **runtime** dependency is justified against the lean-core budget
  (CONTRIBUTING → "Dependency policy (lean core)") and added to
  `RUNTIME_DEPENDENCY_BUDGET` — or N/A.

## Checklist

- [ ] Tests pass locally (`make test` or `pytest`)
- [ ] Lint and format clean (`make lint` and `make format-check`)
- [ ] Type check clean (`make typecheck`) — or known-clean pre-existing issues only
- [ ] No secrets committed (`vibeguard gate --path . --fail-on critical` passes)
- [ ] Linked issue above (or this PR documents why no issue is required)
- [ ] PR title follows conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `style:`, `test:`, `refactor:`, `ci:`)
