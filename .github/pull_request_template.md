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

<!--
Run the full gate — `make ci` runs all seven checks (lint, format-check,
typecheck, docs-check, bench-precision-check, check-versions, test), the same
set GitHub Actions enforces. Listing a subset trains people to skip the drift
guards that most often cause rework.
-->

- `make ci` — _all gates pass_
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

- [ ] `make ci` passes locally (or only known-clean pre-existing mypy issues remain)
- [ ] No secrets committed (`vibeguard gate --path . --fail-on critical` passes)
- [ ] Linked issue above (or this PR documents why no issue is required)
- [ ] PR title follows conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `style:`, `test:`, `refactor:`, `ci:`)
