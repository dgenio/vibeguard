"""Markdown reporter — useful for PR comments."""

from __future__ import annotations

from vibeguard.models import Finding, ScanResult, Severity

_SEV_EMOJI = {
    Severity.INFO: "ℹ️",
    Severity.LOW: "🔵",
    Severity.MEDIUM: "🟡",
    Severity.HIGH: "🔴",
    Severity.CRITICAL: "💀",
}


def render_markdown(result: ScanResult) -> str:
    """Return a Markdown string of the scan result."""
    lines: list[str] = []
    lines.append("## VibeGuard Scan Results\n")

    counts = result.counts()
    total = len(result.findings)

    if total == 0:
        lines.append("✅ **No findings** — scan passed.\n")
    else:
        badges = " | ".join(
            f"{_SEV_EMOJI.get(Severity(k), '')} **{k}**: {v}" for k, v in counts.items() if v > 0
        )
        lines.append(f"**{total} finding(s)** — {badges}\n")

        lines.append("| Severity | Rule | Path | Title |\n| --- | --- | --- | --- |")

        for finding in sorted(result.findings, key=lambda f: f.severity, reverse=True):
            emoji = _SEV_EMOJI.get(finding.severity, "")
            loc = finding.path + (f":{finding.line}" if finding.line else "")
            lines.append(
                f"| {emoji} {finding.severity.value} | `{finding.rule}` "
                f"| `{loc}` | {finding.title} |"
            )

        lines.append("")
        lines.append("### Details\n")
        for finding in sorted(result.findings, key=lambda f: f.severity, reverse=True):
            lines.extend(_finding_detail(finding))

    lines.append(f"\n---\n*Scanned {result.scanned_files} file(s) · policy: {result.policy}*")
    return "\n".join(lines)


def _finding_detail(finding: Finding) -> list[str]:
    emoji = _SEV_EMOJI.get(finding.severity, "")
    loc = finding.path + (f":{finding.line}" if finding.line else "")
    lines = [
        f"#### {emoji} `{finding.id}` — {finding.title}",
        "",
        f"**Path:** `{loc}`  ",
        f"**Severity:** {finding.severity.value}  ",
        f"**Confidence:** {finding.confidence.value}  ",
        "",
        finding.description,
        "",
    ]
    if finding.evidence:
        lines += ["```", finding.evidence, "```", ""]
    lines += [f"**Recommendation:** {finding.recommendation}", ""]
    return lines


_MAX_PR_COMMENT_CHARS = 65536


def render_pr_comment(result: ScanResult, *, gate_passed: bool) -> str:
    """Render a PR-comment-optimized Markdown body."""
    from vibeguard import __version__

    lines: list[str] = []

    # Header
    if gate_passed:
        lines.append("## 🟢 VibeGuard Scan Results — PASS\n")
    else:
        lines.append("## 🔴 VibeGuard Scan Results — FAIL\n")

    total = len(result.findings)
    if total == 0:
        lines.append("**No findings** detected.\n")
    else:
        # Summary table
        counts = result.counts()
        lines.append("| Severity | Count |")
        lines.append("| --- | --- |")
        for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
            count = counts.get(sev.value, 0)
            if count > 0:
                lines.append(f"| {sev.value.capitalize()} | {count} |")
        lines.append("")

        # Blocking findings (HIGH+CRITICAL by default)
        blocking = [f for f in result.findings if f.severity >= Severity.HIGH]
        if blocking:
            lines.append("### Blocking Findings\n")
            for finding in blocking:
                emoji = _SEV_EMOJI.get(finding.severity, "")
                loc = finding.path + (f":{finding.line}" if finding.line else "")
                lines.append(f"- {emoji} **`{finding.id}`** `{loc}` — {finding.title}")
            lines.append("")

        # Non-blocking in collapsible
        non_blocking = [f for f in result.findings if f.severity < Severity.HIGH]
        if non_blocking:
            lines.append(f"<details>\n<summary>{len(non_blocking)} additional findings</summary>\n")
            for finding in non_blocking:
                emoji = _SEV_EMOJI.get(finding.severity, "")
                loc = finding.path + (f":{finding.line}" if finding.line else "")
                lines.append(f"- {emoji} **`{finding.id}`** `{loc}` — {finding.title}")
            lines.append("\n</details>")
            lines.append("")

    # Footer
    lines.append(f"\n---\n*Scanned {result.scanned_files} file(s) · vibeguard v{__version__}*")

    body = "\n".join(lines)

    # Truncation
    if len(body) > _MAX_PR_COMMENT_CHARS:
        budget = _MAX_PR_COMMENT_CHARS - 200  # leave room for notice
        # Cut at line boundary
        cut = body.rfind("\n", 0, budget)
        if cut == -1:
            cut = budget
        body = body[:cut] + "\n\n---\n⚠️ Output truncated — too many findings to display."

    return body
