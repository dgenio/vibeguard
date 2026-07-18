"""Rich console reporter."""

from __future__ import annotations

import contextlib

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vibeguard.models import Finding, ScanResult, Severity
from vibeguard.reporters._format import SEVERITY_PRESENTATION


def _severity_color(severity: Severity) -> str:
    return SEVERITY_PRESENTATION[severity].color


def _severity_icon(severity: Severity) -> str:
    return SEVERITY_PRESENTATION[severity].icon


# Health-score letter grades are a console-only concern (not a Severity), so the
# grade palette stays local to this reporter.
_GRADE_COLORS = {
    "A": "bold green",
    "B": "green",
    "C": "yellow",
    "D": "bold yellow",
    "F": "bold red",
}

# Glyphs this reporter emits that a legacy console encoding (e.g. cp1252 on
# Windows, #167) may be unable to represent: the severity skull, the "no
# findings" check, and the summary bullet.
_GLYPH_PROBE = "☠✓•"


def _harden_console_encoding(con: Console) -> Console:
    """Degrade unencodable glyphs instead of crashing the whole report.

    On a console whose encoding cannot represent :data:`_GLYPH_PROBE` (cp1252 and
    other legacy Windows code pages), Rich would raise ``UnicodeEncodeError``
    mid-render and abort — turning a routine scan into a traceback (#167). Switch
    the underlying stream to ``errors="replace"`` so an unrepresentable glyph
    becomes a placeholder and the findings still print. A UTF-8 console (the
    common case) encodes the probe fine and is left untouched.
    """
    encoding = getattr(con.file, "encoding", None)
    if not encoding:
        return con
    try:
        _GLYPH_PROBE.encode(encoding)
    except (UnicodeError, LookupError):
        reconfigure = getattr(con.file, "reconfigure", None)
        if callable(reconfigure):
            # Stream may already hold buffered data or forbid reconfiguration;
            # if so there is nothing safe to do, so leave it as-is.
            with contextlib.suppress(ValueError, OSError):
                reconfigure(errors="replace")
    return con


console = _harden_console_encoding(Console(stderr=False))


def build_findings_table(result: ScanResult) -> Table:
    """Build the Rich findings table.

    Extracted so tests can render it at a fixed width (e.g. 80 columns)
    without going through the module-level console. See #85.
    """
    # Sort by severity (critical first)
    sorted_findings = sorted(result.findings, key=lambda f: f.severity, reverse=True)

    table = Table(
        title="VibeGuard Findings",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        expand=False,
    )
    # Column sizing balances two constraints:
    #
    # 1. #85 — on narrow (80-col) terminals (tmux, SSH, GitHub Actions logs)
    #    Rich otherwise steals width from every column proportionally,
    #    dropping the severity icon entirely and truncating rule names to 3
    #    chars. ``no_wrap`` + ``min_width`` pin Sev/Rule/Path so they stay
    #    readable, and Title is left wrappable so Rich has a column it can
    #    shrink to fit the table within the terminal — without a wrappable
    #    column, an over-wide table is cropped and Sev collapses again.
    # 2. The GitHub Actions problem matcher
    #    (.github/problem-matchers/vibeguard.json) parses a finding row with
    #    an anchored ``^│ … │$`` regex. Sev (width=10, holds "☠ CRITICAL"),
    #    Rule and Path are ``no_wrap`` + ellipsis, so the severity, rule and
    #    file:line captures always sit on one physical line. Only the
    #    trailing message (Title) may wrap; the matcher still matches the
    #    row's first line and captures file/line correctly.
    table.add_column("Sev", style="bold", width=10, no_wrap=True)
    table.add_column("Rule", min_width=10, no_wrap=True, overflow="ellipsis")
    table.add_column("Path", min_width=12, no_wrap=True, overflow="ellipsis")
    table.add_column("Title", min_width=20)

    for finding in sorted_findings:
        color = _severity_color(finding.severity)
        icon = _severity_icon(finding.severity)
        sev_text = Text(f"{icon} {finding.severity.value.upper()}", style=color)
        loc = finding.path
        if finding.line:
            loc += f":{finding.line}"

        table.add_row(
            sev_text,
            finding.rule,
            loc,
            finding.title,
        )

    return table


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

    sorted_findings = sorted(result.findings, key=lambda f: f.severity, reverse=True)

    console.print(build_findings_table(result))

    if verbose:
        for finding in sorted_findings:
            _print_finding_detail(finding)

    _print_stats(result)

    if result.errors:
        console.print("\n[yellow]Scan errors:[/]")
        for err in result.errors:
            console.print(f"  [yellow]• {err}[/]")


def _print_finding_detail(finding: Finding) -> None:
    color = _severity_color(finding.severity)
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
            color = _severity_color(sev)
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
