# VibeGuard threat model

> **Status:** normative for the Trustworthy Observe work tracked by #284.
> **Version:** 1.0-draft
> **Reviewed:** 2026-08-14
> **Review owner:** VibeGuard maintainers
> **Review cadence:** on every material change to scope resolution, policy, exception semantics, plugin trust, evidence, or protected CI integration, and at least once per minor release while #284 is open.

VibeGuard is a deterministic pre-merge analysis gate. This document defines the security and integrity properties VibeGuard intends to provide while the Trustworthy Observe work is being implemented. It is deliberately narrower than a generic claim that a change is "safe".

A complete VibeGuard run means only that the configured analysis completed over the recorded scope under the recorded policy. **No findings does not mean no vulnerabilities, and continuation does not certify a change as secure.**

## 1. Security goals

VibeGuard should make it difficult for an untrusted change, malformed input, failed analysis component, or compromised coding agent to make an incomplete or policy-weakened evaluation look like a trustworthy complete result.

The primary assets are:

- requested scan scope and its identity;
- execution completeness, skipped work, and diagnostics;
- the final policy decision and stable reason codes;
- immutable finding occurrences and their evidence;
- suppressions, baselines, risk acceptances, approvals, and other dispositions;
- repository policy/configuration and the trusted policy actually applied;
- built-in ruleset and plugin identity/version/provenance;
- generated reports and execution evidence;
- CI credentials and repository write/review authority.

VibeGuard does **not** attempt to prove that code is secure. Its security job is to preserve the truth of what was requested, what actually ran, what evidence was produced, and which policy/exception authority affected the decision.

## 2. Actors

The model includes:

- an honest developer;
- an inexperienced developer who unintentionally weakens a control;
- a maintainer/reviewer;
- an autonomous coding agent;
- a compromised or prompt-injected coding agent;
- a malicious pull-request author;
- a malicious dependency or generated repository content;
- a malicious or defective plugin/rule provider;
- a compromised CI environment or workflow dependency;
- a policy/configuration author;
- a risk/exception approver.

Repository metadata may record a claimed human/reviewer identity, but VibeGuard does not by itself cryptographically verify that identity.

## 3. Trust boundaries

### 3.1 Untrusted evaluated content

Repository files, diffs, patches, generated content, paths, symlinks, filenames, and instructions embedded in code/comments/docs are untrusted input. They must not be able to silently alter the scope or policy that evaluates them.

### 3.2 Scope resolution

Git, diff, staged, patch, and explicit-path resolution form a trust boundary. A requested scope must not silently fall back to another scope and then be reported as the requested analysis. Scope identity and any skipped/unreadable content belong in execution evidence. See #285 and #288.

### 3.3 Policy and exception material

Repository-local VibeGuard config, ignores, suppressions, baselines, policy packs, thresholds, rule enablement, and plugin requirements are potentially controlled by the same change being evaluated. Under the `integrity` profile they are therefore not sufficient authority to authorize that change.

**Maintainer decision:** `integrity` evaluates against a trusted base-branch or explicit out-of-band policy. An untrusted patch cannot redefine the policy that authorizes that same patch. Same-change protection is specified in #132.

### 3.4 Rules and plugins

Built-in rules are part of the VibeGuard release trust boundary. Third-party plugins execute Python in-process and are **trusted code, not sandboxed rules**. Installing or allow-listing a plugin is an operator/repository trust decision and must not be driven by untrusted scanned content.

Policy distinguishes:

- **required trusted components** — discovery/load/validation/execution failure makes required analysis incomplete and blocks `integrity`;
- **optional extensions** — failure is explicit and may produce `degraded` only when policy permits that degradation.

See #184 and #286.

### 3.5 Local filesystem

Path normalization, traversal, symlink behavior, rename/deletion handling, ignored files, Unicode/bidirectional text, unreadable files, and size/resource limits are security-relevant because they can change what was actually inspected. Required content that cannot be evaluated must not be silently counted as complete.

### 3.6 CI and workflow authority

GitHub Actions runners, checkout state, workflow dependencies, permissions, and repository tokens are trusted only to the extent of their granted authority. VibeGuard cannot protect against a CI host already compromised with equivalent authority to alter the evaluated source, trusted policy, or produced evidence.

Protected integrations should use least privilege and should separate the untrusted change from the trusted policy/review authority used for `integrity` decisions.

### 3.7 Evidence and outputs

Console, JSON, Markdown, SARIF, Action output, and future signed evidence must derive from one recorded execution/decision state. Failure to serialize required evidence or disagreement between authoritative outputs is an integrity failure, not an ordinary finding.

### 3.8 External analyzers and LLMs

Any optional external analyzer or explanation adapter is a separate trust and data-egress boundary. Prompt injection in scanned content must not be allowed to change VibeGuard policy or exception authority. Current trustworthy-profile guarantees do not depend on an LLM deciding whether a finding is enforceable.

## 4. Profile guarantees

The semantics below are normative targets coordinated with #286. Where implementation work remains open, this document describes the guarantee required before the corresponding profile claim may be considered complete.

### `observe`

`observe` is an evidence-collection/advisory profile:

- detection findings are advisory;
- execution status and diagnostics remain visible;
- ordinary findings do not convert continuation into a security certification;
- optional degradation is explicit;
- incomplete analysis is never represented as a complete safe result;
- invalid invocation/configuration remains an error rather than being disguised as a finding.

A workflow may continue after `observe`; that fact means only that the selected profile permits continuation.

### `integrity`

`integrity` inherits the advisory finding semantics of `observe` and adds integrity enforcement over the analysis process:

- incomplete required analysis blocks;
- required rule/plugin discovery, validation, initialization, execution, or required output conversion failure blocks;
- invalid or inconsistent decision/evidence generation blocks;
- unauthorized same-change weakening of policy/config/baseline/suppression/ignore/rule/plugin requirements blocks;
- the policy applied to the decision comes from a trusted base or explicit out-of-band source;
- ordinary detection findings remain advisory during the Trustworthy Observe validation phase.

A complete `integrity` result therefore means: the configured required analysis completed over the recorded scope under the recorded trusted policy and the integrity process did not detect a prohibited self-weakening or required-component failure. It does **not** mean the code is secure.

## 5. Exception and disposition authority

Per #132, findings are immutable occurrences. Suppression, baseline, risk acceptance, false-positive classification, expiry, and remediation are separate dispositions over those occurrences.

Minimum authority expectations are:

| Action | Minimum authority |
| --- | --- |
| Local advisory suppression | Developer |
| Repository suppression affecting policy | Code owner or named security owner |
| Change enforcement profile | Repository administrator / trusted policy owner |
| Create or update baseline | Maintainer with recorded review |
| Accept high-impact risk | Named risk owner |
| Agent-generated exception | Independent human approval; never self-approved |

Repository metadata can record the asserted authority and review trail; it is not by itself proof of verified human identity.

## 6. Residual-risk rule

A P0 threat does not become acceptable merely because it is documented. A residual risk may remain only when all of the following hold:

1. the residual risk is explicit and bounded;
2. an owner/reviewer is identified;
3. the public profile guarantee is narrowed so it does not contradict the residual risk;
4. detection/evidence exists where practical;
5. an adversarial test is linked where practical;
6. the affected capability is blocked when the remaining risk would invalidate the stated guarantee.

If those conditions cannot be met, the affected capability/claim does not ship as part of the trustworthy profile.

## 7. Threat traceability

The table distinguishes **current** protections from planned work. An open issue is not itself a mitigation; it records the work required before the stronger claim can be made.

| Threat | Current mitigation / posture | Required/planned mitigation | Residual risk | Evidence signal | Adversarial test |
| --- | --- | --- | --- | --- | --- |
| Requested diff/patch silently falls back to another scope | Scope modes are explicit and diagnostics exist for several Git failures | First-class requested/effective scope identity and fail-closed required-scope semantics (#285, #286) | Until complete, callers must inspect diagnostics; do not claim scope-complete integrity | requested/effective mode, base/patch identity, files discovered/examined/skipped | #288 scope-fallback cases |
| Empty/incomplete scan represented as success | Diagnostics and `--strict-errors` expose several degraded failures | Explicit `ScanExecution` status (`complete/degraded/incomplete/error`) and separate decision model (#286) | Existing exit behavior is not a proof of completeness | execution status + reason codes | #288 incomplete/empty cases |
| Parser/rule failure hidden as a low-severity finding | Rule errors can surface as diagnostics | Required component failure -> `incomplete`; `integrity` blocks (#286) | Optional components may degrade only by policy | failed rules + diagnostics + decision reason | #288 required-rule failure |
| Required plugin missing/fails | Plugin failures are discoverable but current contract is incomplete | Validate plugin contracts; record provenance; required vs optional semantics (#184) | Plugins remain trusted in-process code | required/completed/failed plugin identity | #288 plugin cases |
| Malicious/defective plugin executes code | Plugins are opt-in Python extensions | Explicit trust/allow-list guidance and provenance (#184) | **Accepted/narrowed:** no plugin sandbox is claimed | package/version/entry-point identity | contract/load-failure tests in #184/#288 |
| Same-change config/policy weakening | Existing config is visible but can be part of the evaluated tree | Trusted-base/out-of-band applied policy; same-change detection/block (#132, #286) | Until wired, do not claim same-change-safe integrity | applied policy/config digest + detected policy changes | #288 self-weakening cases |
| Same-change suppression/baseline self-authorizes | Missing-reason checks exist for inline suppressions | Immutable occurrence + governed dispositions; self-change cannot affect current `integrity` decision (#132) | Legacy destructive behavior must not be authoritative evidence | occurrence + disposition source/authority/status | #288 suppression/baseline cases |
| Expired/overbroad/forged exception metadata | Central suppressions/baselines have limited current metadata | Validate owner/reason/scope/lifecycle/approval and explicit rejection/expiry states (#132, #255) | Repository identity metadata is not cryptographic identity | disposition owner/reviewer/source/expiry + rejection reason | #288 exception lifecycle cases |
| Fingerprint collision or stale baseline identity | Stable identifiers exist for current findings | Version fingerprint semantics and aging/lifecycle (#181, #255) | Collision resistance is bounded by chosen scheme | fingerprint scheme/version + source identity | #288 stale/collision fixtures |
| Path traversal/symlink/rename/deletion/Unicode edge cases change scope | Scanner has path/ignore/binary/size handling and explicit patch reconstruction | Scope hardening and adversarial fixtures (#285, #288) | Platform filesystem behavior remains part of trusted runtime | files discovered/examined/skipped + diagnostics | #288 path cases |
| Regex/parser resource exhaustion | Scanner uses bounded logic in several rules | Per-rule/parser adversarial limits and explicit incomplete status on required failure (#288) | Cannot guarantee arbitrary input is cheap | component timing/failure diagnostic where available | #288 resource-exhaustion fixtures |
| CLI/Action/SARIF/JSON decisions diverge | Reporters share scanner result structures | One versioned execution/decision source and consistency tests (#286, #287, #288) | Human prose may differ; authoritative semantics must not | schema version + decision/reason codes in outputs | cross-output golden tests |
| Evidence/report generation fails or is tampered with | Output generation errors are visible | Required evidence failure blocks `integrity`; signing/attestation tracked separately (#287) | No cryptographic proof until signing exists | output generation status/digest/version | #288 evidence-failure cases |
| Findings/evidence leak secrets/source | Outputs are intentionally bounded in several surfaces | Evidence minimization/redaction review in #287/#288 | Some findings necessarily contain bounded source evidence | redaction/minimization metadata and schema | secret-containing synthetic fixture |
| Prompt injection targets coding agent/optional LLM analyzer | Core deterministic rule decision does not require an LLM | Keep policy/exception authority outside model output; treat external analyzer as untrusted advisory input | Cannot stop a compromised external model/client from behaving maliciously | analyzer provenance + advisory-only classification | prompt-injection synthetic fixture |
| CI token/workflow permission escalation | Standard GitHub permission controls are available | Least-privilege protected workflow guidance and integrity fixtures (#288) | A CI host compromised with equivalent write authority is outside the guarantee | workflow/ref/checkout identity where integration exposes it | protected-workflow review fixture |
| Untrusted change alters plugin requirements/allow-list | Config changes are inspectable | Requirements come from trusted policy; same-change weakening blocks (#132, #184) | Until wired, do not claim protected plugin policy | applied plugin requirement set + policy digest | #288 plugin-policy weakening |

## 8. Explicit non-guarantees

VibeGuard does not currently guarantee:

- complete vulnerability detection;
- enforcement-grade precision for current detection rules;
- AI authorship detection;
- protection from a compromised CI host with equivalent authority;
- sandboxing of trusted Python plugins;
- cryptographic proof of evidence until signing/attestation is implemented;
- verified human identity solely from repository metadata;
- replacement of SAST, secret, dependency, IaC, or supply-chain scanners;
- safety merely because a run produced no findings.

## 9. Review requirements for changes

A contribution requires explicit threat-model review when it changes any of:

- scan scope selection/resolution or path handling;
- `observe`/`integrity` execution or decision semantics;
- policy/config precedence or trusted-policy sourcing;
- suppressions, baselines, ignores, risk acceptance, or other dispositions;
- plugin/rule discovery, trust, requirement, or failure semantics;
- execution diagnostics/completeness;
- evidence schemas, serialization, upload, or future signing;
- CI checkout, permissions, identity, or protected integration behavior.

Reviewers should identify the affected threat-table rows, update current/planned mitigation status, and add or update the enforcing test/gate. If a hard guarantee cannot be mechanically exercised, label it explicitly as review policy rather than implying the implementation enforces it.

## 10. Related normative work

- #284 — Trustworthy Observe parent
- #285 — scan-scope semantics
- #286 — explicit execution status and `observe`/`integrity` decisions
- #287 — versioned execution/evidence contract
- #288 — adversarial end-to-end scenarios
- #132 — governed dispositions and same-change protection
- #181 — stable finding/fingerprint identity
- #184 — plugin contract and required/optional execution
- #255 — baseline/disposition lifecycle and aging

Until the linked implementation issues land, this document is the normative target and a release/claim constraint — **not evidence that the target has already been implemented**.
