# VibeGuard Roadmap

VibeGuard is **the deterministic pre-merge safety gate for AI-generated
diffs**. This page explains where the project is heading and why, so a
first-time contributor can tell what work is welcome, what is a v1 blocker,
and what is intentionally out of scope.

The guiding principle for v1 is **trust before breadth**: a gate that teams
enforce in CI has to be boring, predictable, and easy to adopt before it is
clever. We harden and document the existing gate before adding many new
rules.

---

## Now — trust hardening and v1 readiness

The current focus is making VibeGuard safe to enforce as a default PR gate.

- Fail-closed behaviour on bad paths, malformed config, and empty scans
  (the [stability contract](stability-contract.md) documents the guarantees).
- A published [stability contract](stability-contract.md) so teams know what
  is safe to pin.
- Release discipline: README, PyPI, GitHub releases, tags, and action
  snippets all agree on one adoption path (see the
  [release checklist](release-checklist.md)).
- Adoption UX: one-command onboarding for GitHub Actions and config
  generation.

## Next — adoption UX, benchmarks, comparison docs

- A reproducible [benchmark & evaluation report](benchmark.md) for
  AI-diff failure modes (throughput + false-positive baseline).
- A [comparison guide](comparison.md) vs Semgrep, CodeQL, gitleaks,
  Dependabot, and linters — when to reach for VibeGuard and when not to.
- Scenario-based examples that look like real PRs
  ([`examples/pr-scenarios/`](../examples/pr-scenarios)).
- Contributor scaffolding for new rules.

## Later — ecosystem and richer integrations

- A growing plugin ecosystem on top of the
  [plugin API](plugin-api.md) (`PLUGIN_API_VERSION`).
- Additional opt-in policy packs.
- Richer editor / CI integrations built on the stable JSON, SARIF, and
  diagnostics outputs.

## Non-goals

VibeGuard deliberately does **not** try to be:

- A full SAST replacement (use Semgrep, CodeQL, Bandit).
- A CVE / dependency-vulnerability scanner (use Dependabot, pip-audit,
  npm audit, Snyk).
- A historical secret scanner (use gitleaks / truffleHog over full history).
- A network- or LLM-based analyzer. The core gate stays **offline,
  deterministic, and API-key-free** — that is the whole product thesis.

These are not "not yet" — they are intentional boundaries. Coverage that
requires the network or an LLM in the loop belongs in a different tool, or in
an opt-in plugin, not in the core gate.

---

## Issue label taxonomy

The backlog is organised around an **evidence-first funnel** (#170): labels make
visible *why* an issue is open, *when* it may start, and *what* evidence or
dependency unlocks it — so speculative ideas, validation work, maintenance, and
immediate product-risk fixes don't compete in one undifferentiated queue.

**Priority**

| Label | Meaning |
|---|---|
| `priority:p0` | Blocks trustworthy execution, policy integrity, or evidence validity |
| `priority:p1` | Important work sequenced after P0, or required for field validation |

A blocked or evidence-gated idea does **not** earn a priority label just because
it is attractive.

**Status**

| Label | Meaning |
|---|---|
| `status:blocked` | Cannot begin until a named dependency or decision is complete |
| `status:validation` | Experiment, corpus, benchmark, or evidence-gathering work |
| `status:maintenance` | Repo quality, CI, contributor, release, or dependency hygiene |

**Evidence and scope**

| Label | Meaning |
|---|---|
| `needs-evidence` | Requires user, corpus, benchmark, or comparative evidence before implementation |
| `rule-candidate` | Candidate detection / change-integrity signal, not an approved rule |
| `superseded` | Retained only as historical context after consolidation |
| `out-of-scope` | Deliberately outside the current product boundary (see Non-goals above) |

Keep the existing domain labels (`security`, `reliability`, `testing`,
`documentation`, `product`, …) where they add signal; avoid a label for every
subsystem or integration.

> Maintainer note: creating and applying these labels is a repository-admin
> action. This page is the source of truth for what each label means; the labels
> themselves are created and applied to issues over time. A blocked issue title
> may temporarily use `[Blocked by #NNN]` until the `status:blocked` label is
> applied.

## What makes a good VibeGuard rule

A rule is a good fit for **core** when it is:

1. **Deterministic** — same input, same finding, every time. No network, no
   randomness, no LLM.
2. **Fast** — pattern/AST-level work that keeps the whole scan in
   single-digit seconds.
3. **Aimed at an AI-coding failure mode** — secrets in new files, packaging
   leaks, disabled security controls, "trust all certs", commented-out auth,
   risky-diff signals. Not general style or deep dataflow.
4. **Low false-positive** — or, if it is a *risk signal* rather than a
   vulnerability claim (like `risky_diff`), clearly framed as "look at this,"
   not "this is exploitable."
5. **Stable-ID'd and tested** — a `<PREFIX>-<NAME>` finding ID plus positive
   and negative fixtures.

See [`how-to-add-a-rule.md`](how-to-add-a-rule.md) for the mechanics.

## Core rule vs plugin

Prefer a **plugin** (via the [plugin API](plugin-api.md)) over a core rule
when the detection is:

- organisation- or stack-specific (your internal conventions, a single
  vendor's SDK);
- opinionated in a way not every user would want on by default;
- experimental, or evolving faster than core's stability contract allows.

Core rules carry a stability promise (see the
[stability contract](stability-contract.md)); plugins let you move fast
without waiting on that promise. When in doubt, prototype as a plugin and
propose promotion to core once the pattern and finding IDs are stable.

---

## Contributing against this roadmap

A first-time contributor's best entry points: issues labelled
`status:maintenance` (repo quality, CI, docs, contributor experience),
false-positive reports with a clear repro, and docs. Larger work (new rules,
integrations) is most likely to land when it matches the **Now/Next** focus
above. If you want to work on something in **Later**
or a **Non-goal**, open an issue first so we can align before you invest
time. See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for setup and conventions.
