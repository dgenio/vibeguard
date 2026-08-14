# Security Policy

VibeGuard is a security-focused pre-merge safety gate, so responsible vulnerability reporting matters. This policy explains which versions and findings are in scope, how to report issues privately, and what information helps maintainers triage quickly.

For the security boundaries and exact guarantees/non-guarantees of the Trustworthy Observe work, see the [normative threat model](docs/threat-model.md). In particular, a complete or no-findings scan is **not** a certification that a change is secure.

## Supported versions

VibeGuard is currently pre-1.0. Security fixes are handled for:

| Version / branch | Supported |
| --- | --- |
| Latest release on PyPI | Yes |
| `main` branch | Yes |
| Older releases | Best effort only |

If a fix affects users of a published release, maintainers should publish a patched release and note the fixed version in the advisory or release notes.

## In-scope security issues

Please report issues that could affect VibeGuard users or the integrity of VibeGuard's results, including:

- Vulnerabilities in VibeGuard itself, such as path traversal, unsafe file handling, command execution, or code/config injection.
- Bugs that allow crafted repositories, config files, lockfiles, manifests, or source files to crash scans or bypass expected safety checks.
- False negatives in critical rules where VibeGuard reports a high-risk pattern as safe, especially for secrets, package leaks, dependency risks, or disabled security controls.
- Dependency vulnerabilities that materially affect VibeGuard's scanner, CLI, packaging, or release security.
- Release, packaging, or CI issues that could let a compromised artifact be published as VibeGuard.

## Out of scope

The following are usually better handled as normal issues or discussions:

- False positives, noisy rules, wording changes, or feature requests.
- Findings in a repository scanned by VibeGuard, unless the issue is caused by VibeGuard mishandling that input.
- Reports that only say a dependency is outdated without showing an exploitable impact for VibeGuard.
- Social engineering, physical attacks, spam, denial-of-service against project infrastructure, or attempts to access accounts you do not own.
- Publicly disclosing an unpatched vulnerability before maintainers have had a reasonable chance to respond.

## How to report a vulnerability

Use GitHub's private vulnerability reporting flow if it is enabled for this repository:

1. Open the repository's **Security** tab.
2. Select **Report a vulnerability**.
3. Include the details listed in the report template below.

If private vulnerability reporting is not enabled, please open a minimal public issue asking maintainers to enable private reporting or provide a security contact. Do **not** include exploit details, secrets, proof-of-concept payloads, or vulnerable private data in a public issue.

## Report template

A useful report includes:

- A short title and severity estimate.
- Affected VibeGuard version, commit, or installation method.
- Operating system and Python version.
- Whether the issue affects `vibeguard scan`, `vibeguard gate`, package publishing, CI, or another path.
- Minimal reproduction steps using a small synthetic repository or fixture.
- Expected result vs actual result.
- Security impact and any known mitigations.
- Whether the issue is already public anywhere else.

Please keep examples synthetic. Do not include real third-party secrets or private customer code.

## Maintainer triage process

Maintainers should aim to:

1. Acknowledge the report and confirm whether it is in scope.
2. Reproduce the issue using the smallest safe fixture possible.
3. Assign an impact level based on exploitability and user exposure.
4. Prepare a fix, regression test, and release/advisory notes where appropriate.
5. Credit the reporter if they want attribution and the report is valid.

Maintainers will aim to acknowledge valid-looking reports within five business days and provide an initial triage assessment within ten business days. Timelines may vary based on severity, exploitability, and maintainer availability.

Suggested severity guide:

| Severity | Examples |
| --- | --- |
| Critical | Remote code execution, credential exposure in release tooling, or a reliable bypass of critical secret detection across common inputs. |
| High | Crafted input causes unsafe file access, command execution in normal usage, or a broad false negative for high-impact security controls. |
| Medium | Denial of service from realistic inputs, significant scanner bypasses with narrow conditions, or dependency issues with plausible impact. |
| Low | Hard-to-trigger crashes, minor information disclosure, documentation-only security confusion, or low-impact dependency findings. |

## Safe harbor

Security research is welcome when it is lawful, good-faith, and limited to systems and data you own or are explicitly authorized to test. Do not attack live infrastructure, disrupt users, access private data, or bypass access controls. Reports that follow this policy will be treated as helpful contributions.
