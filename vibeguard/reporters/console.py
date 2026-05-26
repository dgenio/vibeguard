"""Rich console reporter."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vibeguard.models import Finding, ScanResult, Severity

_SEVERITY_COLORS = {
    Severity.INFO: "dim white",
    Severity.LOW: "cyan",
    Severity.MEDIUM: "yellow",
    Severity.HIGH: "red",
    Severity.CRITICAL: "bold red",
}

_SEVERITY_ICONS = {
    Severity.INFO: "ℹ",
    Severity.LOW: "↓",
    Severity.MEDIUM: "⚠",
    Severity.HIGH: "✗",
    Severity.CRITICAL: "☠",
}

_GRADE_COLORS = {
    "A": "bold green",
    "B": "green",
    "C": "yellow",
    "D": "bold yellow",
    "F": "bold red",
}

console = Console(stderr=False)


def render_findings(result: ScanResult, verbose: bool = False) -> None:
    """Print findings table and summary to the console."""
    if not result.findings:
        console.print(
            Panel(
                "[bold green]✓ No findings[/] — nothing to worry about.",
                title="[bold]VibeGuard[/]",
                border_style="green",
            )
        )
        _print_stats(result)
        return

    # Sort by severity (critical first)
    sorted_findings = sorted(result.findings, key=lambda f: f.severity, reverse=True)

    table = Table(
        title="VibeGuard Findings",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        expand=False,
    )
    # Width=10 ensures "☠ CRITICAL" (the widest label) renders on a single
    # line so the GitHub Actions problem matcher in
    # .github/problem-matchers/vibeguard.json can match the row in one shot.
    table.add_column("Sev", style="bold", width=10, no_wrap=True, min_width=10)
    table.add_column("Rule", width=16, no_wrap=True, min_width=12)
    table.add_column("Path", width=40)
    table.add_column("Title", width=50)

    for finding in sorted_findings:
        color = _SEVERITY_COLORS[finding.severity]
        icon = _SEVERITY_ICONS[finding.severity]
        sev_text = Text(f"{icon} {finding.severity.value.upper()}", style=color)
        loc = finding.path
        if finding.line:
            loc += f":{finding.line}"

        table.add_row(
            sev_text,
            finding.rule,
            loc[:40],
            finding.title[:50],
        )

    console.print(table)

    if verbose:
        for finding in sorted_findings:
            _print_finding_detail(finding)

    _print_stats(result)

    if result.errors:
        console.print("\n[yellow]Scan errors:[/]")
        for err in result.errors:
            console.print(f"  [yellow]• {err}[/]")


def _print_finding_detail(finding: Finding) -> None:
    color = _SEVERITY_COLORS[finding.severity]
    lines = [
        f"[bold]{finding.title}[/]",
        f"  {finding.description}",
        f"  [dim]Recommendation:[/] {finding.recommendation}",
    ]
    if finding.evidence:
        lines.append(f"  [dim]Evidence:[/] [italic]{finding.evidence}[/]")
    console.print(
        Panel(
            "\n".join(lines),
            title=f"[{color}]{finding.id}[/] {finding.path}"
            + (f":{finding.line}" if finding.line else ""),
            border_style=color,
        )
    )


def _print_stats(result: ScanResult) -> None:
    counts = result.counts()
    total = len(result.findings)

    parts = []
    for sev in reversed(list(Severity)):
        c = counts[sev.value]
        if c:
            color = _SEVERITY_COLORS[sev]
            parts.append(f"[{color}]{sev.value}: {c}[/]")

    summary = f"[bold]{total}[/] finding(s)"
    if parts:
        summary += "  |  " + "  ".join(parts)

    score = result.health_score
    grade_color = _GRADE_COLORS.get(score.grade, "white")
    score_text = f"health: [{grade_color}]{score.total}/100 ({score.grade})[/]"

    console.print(
        f"\n  Scanned [bold]{result.scanned_files}[/] file(s)  •  "
        f"{summary}  •  {score_text}  •  policy: [bold]{result.policy}[/]\n"
    )
