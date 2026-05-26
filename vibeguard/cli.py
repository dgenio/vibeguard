"""VibeGuard CLI — entry point."""

from __future__ import annotations

import contextlib
import platform
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from rich.console import Console

from vibeguard import __version__
from vibeguard.config import DEFAULT_CONFIG_YAML, VibeGuardConfig
from vibeguard.git import get_git_metadata
from vibeguard.models import Severity
from vibeguard.reporters.annotations import render_annotations
from vibeguard.reporters.console import render_findings
from vibeguard.reporters.diagnostics import render_diagnostics
from vibeguard.reporters.json_reporter import print_json
from vibeguard.reporters.markdown import render_markdown, render_pr_comment
from vibeguard.reporters.sarif import render_sarif
from vibeguard.scanner import run_scan

app = typer.Typer(
    name="vibeguard",
    help="Guardrails for vibe-coded software.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"vibeguard {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """VibeGuard — a pre-merge safety gate for AI-generated code."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command()
def init(
    path: Annotated[
        Path,
        typer.Option("--path", help="Directory to create vibeguard.yaml in"),
    ] = Path("."),
) -> None:
    """Create a default vibeguard.yaml configuration file."""
    config_path = path / "vibeguard.yaml"
    if config_path.exists():
        err_console.print(f"[yellow]vibeguard.yaml already exists at {config_path}. Skipping.[/]")
        raise typer.Exit(0)

    path.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG_YAML)
    err_console.print(f"[green]✓[/] Created [bold]{config_path}[/]")
    err_console.print("  Edit it to customise your policy, ignores, and enabled rules.")


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Show version, Python, platform, and install path."""
    import vibeguard

    install_path = Path(vibeguard.__file__).resolve().parent
    lines = [
        f"vibeguard {__version__}",
        f"Python {sys.version.split()[0]}",
        f"Platform: {platform.platform()}",
        f"Install path: {install_path}",
    ]
    for line in lines:
        typer.echo(line)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@app.command()
def validate(
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Directory to search for vibeguard.yaml"),
    ] = Path("."),
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to vibeguard.yaml"),
    ] = None,
) -> None:
    """Validate a vibeguard.yaml config file and exit 0 (valid) or 1 (invalid)."""
    config_path = config or (path / "vibeguard.yaml")
    if not config_path.exists():
        err_console.print(f"[red]Config file not found: {config_path}[/]")
        raise typer.Exit(1)

    try:
        VibeGuardConfig.load(config_path)
    except ValidationError as exc:
        err_console.print(f"[red]Invalid config: {config_path}[/]\n")
        for error in exc.errors():
            loc = " → ".join(str(p) for p in error["loc"])
            err_console.print(f"  [bold]{loc}[/]: {error['msg']}")
        raise typer.Exit(1) from None
    except Exception as exc:
        err_console.print(f"[red]Error reading config: {exc}[/]")
        raise typer.Exit(1) from None

    typer.echo(f"✓ Config is valid: {config_path}")


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


def _validate_output_options(
    json_output: bool,
    markdown_output: bool,
    pr_comment: bool = False,
    sarif: bool = False,
    annotations: bool = False,
    diagnostics: bool = False,
) -> None:
    """Fail fast if mutually exclusive output options are both set."""
    count = sum([json_output, markdown_output, pr_comment, sarif, annotations, diagnostics])
    if count > 1:
        err_console.print(
            "[red]Error: output format options are mutually exclusive. Choose one.[/]"
        )
        raise typer.Exit(2)


@app.command()
def scan(
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Repository or directory to scan"),
    ] = Path("."),
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to vibeguard.yaml"),
    ] = None,
    diff: Annotated[
        bool,
        typer.Option("--diff", help="Scan only changed files (requires git)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output findings as JSON"),
    ] = False,
    markdown_output: Annotated[
        bool,
        typer.Option("--markdown", help="Output findings as Markdown"),
    ] = False,
    sarif_output: Annotated[
        bool,
        typer.Option("--sarif", help="Output findings as SARIF"),
    ] = False,
    annotations_output: Annotated[
        bool,
        typer.Option("--annotations", help="Output as GitHub Actions annotations"),
    ] = False,
    diagnostics_output: Annotated[
        bool,
        typer.Option("--diagnostics", help="Output as diagnostics JSON array"),
    ] = False,
    fail_on: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            help="Severity threshold — informational only in scan (use gate for enforcement) [info|low|medium|high|critical]",
        ),
    ] = None,
    pr_comment: Annotated[
        bool,
        typer.Option("--pr-comment", help="Output as a PR-comment-optimized Markdown body"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed finding descriptions"),
    ] = False,
) -> None:
    """Scan a repository for risky AI-generated code patterns."""
    _validate_output_options(
        json_output,
        markdown_output,
        pr_comment,
        sarif_output,
        annotations_output,
        diagnostics_output,
    )
    _validate_path(path)
    cfg = _load_config(config, path)
    if fail_on:
        cfg.fail_on = _parse_severity(fail_on)

    git_meta = None
    if diff:
        git_meta = get_git_metadata(path.resolve())
        if not git_meta.is_available:
            err_console.print(
                f"[yellow]⚠ Git not available: {git_meta.error}. Falling back to full scan.[/]"
            )
            diff = False

    result = run_scan(path, cfg, diff_only=diff, git_meta=git_meta)

    if json_output:
        print_json(result)
    elif markdown_output:
        typer.echo(render_markdown(result))
    elif pr_comment:
        typer.echo(render_pr_comment(result, gate_passed=True))
    elif sarif_output:
        typer.echo(render_sarif(result))
    elif annotations_output:
        typer.echo(render_annotations(result))
    elif diagnostics_output:
        typer.echo(render_diagnostics(result))
    else:
        render_findings(result, verbose=verbose)

    if result.errors:
        for err in result.errors:
            err_console.print(f"[yellow]⚠ {err}[/]")

    # scan command: always exit 0 (informational)


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


@app.command()
def gate(
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Repository or directory to scan"),
    ] = Path("."),
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to vibeguard.yaml"),
    ] = None,
    diff: Annotated[
        bool,
        typer.Option("--diff", help="Scan only changed files (requires git)"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output findings as JSON"),
    ] = False,
    markdown_output: Annotated[
        bool,
        typer.Option("--markdown", help="Output findings as Markdown"),
    ] = False,
    sarif_output: Annotated[
        bool,
        typer.Option("--sarif", help="Output findings as SARIF"),
    ] = False,
    annotations_output: Annotated[
        bool,
        typer.Option("--annotations", help="Output as GitHub Actions annotations"),
    ] = False,
    diagnostics_output: Annotated[
        bool,
        typer.Option("--diagnostics", help="Output as diagnostics JSON array"),
    ] = False,
    fail_on: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            help="Severity threshold for non-zero exit [info|low|medium|high|critical]",
        ),
    ] = None,
    pr_comment: Annotated[
        bool,
        typer.Option("--pr-comment", help="Output as a PR-comment-optimized Markdown body"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed finding descriptions"),
    ] = False,
) -> None:
    """Scan and exit non-zero if blocking findings are found (for CI gates)."""
    _validate_output_options(
        json_output,
        markdown_output,
        pr_comment,
        sarif_output,
        annotations_output,
        diagnostics_output,
    )
    _validate_path(path)
    cfg = _load_config(config, path)
    if fail_on:
        cfg.fail_on = _parse_severity(fail_on)

    git_meta = None
    if diff:
        git_meta = get_git_metadata(path.resolve())
        if not git_meta.is_available:
            err_console.print(
                f"[yellow]⚠ Git not available: {git_meta.error}. Falling back to full scan.[/]"
            )
            diff = False

    result = run_scan(path, cfg, diff_only=diff, git_meta=git_meta)

    threshold = cfg.fail_on
    gate_passed = not result.has_blocking(threshold)

    if json_output:
        print_json(result)
    elif markdown_output:
        typer.echo(render_markdown(result))
    elif pr_comment:
        typer.echo(render_pr_comment(result, gate_passed=gate_passed))
    elif sarif_output:
        typer.echo(render_sarif(result))
    elif annotations_output:
        typer.echo(render_annotations(result))
    elif diagnostics_output:
        typer.echo(render_diagnostics(result))
    else:
        render_findings(result, verbose=verbose)

    if result.errors:
        for err in result.errors:
            err_console.print(f"[yellow]⚠ {err}[/]")

    if not gate_passed:
        err_console.print(
            f"\n[bold red]✗ Gate failed:[/] findings at or above "
            f"[bold]{threshold.value}[/] severity detected.\n"
        )
        raise typer.Exit(1)
    else:
        err_console.print(
            f"\n[bold green]✓ Gate passed:[/] no findings at or above "
            f"[bold]{threshold.value}[/] severity.\n"
        )


# ---------------------------------------------------------------------------
# publish-check
# ---------------------------------------------------------------------------


@app.command("publish-check")
def publish_check(
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Package root directory"),
    ] = Path("."),
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to vibeguard.yaml"),
    ] = None,
    ecosystem: Annotated[
        str | None,
        typer.Option(
            "--ecosystem", help="Ecosystem to simulate [auto|npm|python-sdist|python-wheel]"
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
    markdown_output: Annotated[
        bool,
        typer.Option("--markdown", help="Output as Markdown"),
    ] = False,
    fail_on: Annotated[
        str | None,
        typer.Option("--fail-on", help="Severity threshold for non-zero exit"),
    ] = None,
    manifest_out: Annotated[
        Path | None,
        typer.Option("--manifest-out", help="Write manifest JSON to this path"),
    ] = None,
) -> None:
    """Simulate a package publish and scan for risky files."""
    import json as json_mod

    from vibeguard.config import apply_policy_suppressions
    from vibeguard.publish.runner import EcosystemChoice, run_publish_check

    _validate_output_options(json_output, markdown_output)
    cfg = _load_config(config, path)

    # Check if disabled in config
    if not cfg.publish_check.enabled:
        err_console.print("[dim]publish-check disabled in config.[/]")
        typer.echo("publish-check disabled")
        return

    # Determine ecosystem
    eco: EcosystemChoice = "auto"
    if ecosystem:
        valid_ecosystems = ("auto", "npm", "python-sdist", "python-wheel")
        if ecosystem not in valid_ecosystems:
            err_console.print(
                f"[red]Invalid ecosystem: {ecosystem!r}. "
                f"Valid options: {', '.join(valid_ecosystems)}[/]"
            )
            raise typer.Exit(2)
        eco = ecosystem  # type: ignore[assignment]
    elif cfg.publish_check.ecosystem != "auto":
        eco = cfg.publish_check.ecosystem  # type: ignore[assignment]

    # Determine threshold
    threshold = cfg.fail_on
    if fail_on:
        threshold = _parse_severity(fail_on)
    elif cfg.publish_check.fail_on:
        with contextlib.suppress(ValueError):
            threshold = Severity(cfg.publish_check.fail_on)

    manifest, result = run_publish_check(path, cfg, ecosystem=eco)

    # Apply suppressions
    if cfg.suppressions and result.findings:
        active, _warnings = apply_policy_suppressions(result.findings, cfg.suppressions)
        result = result.model_copy(update={"findings": active})

    # Write manifest if requested
    if manifest_out:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json_mod.dumps(manifest.model_dump(), indent=2))

    # Output
    if json_output:
        payload = {
            "manifest": manifest.model_dump(),
            "result": result.model_dump(),
        }
        typer.echo(json_mod.dumps(payload, indent=2))
    elif markdown_output:
        typer.echo(render_markdown(result))
    else:
        render_findings(result)

    # Gate logic
    gate_passed = not result.has_blocking(threshold)
    if gate_passed:
        err_console.print("[bold green]✓ publish-check passed[/]")
    else:
        err_console.print("[bold red]✗ publish-check failed[/]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# explain
# ---------------------------------------------------------------------------

_FINDING_EXPLANATIONS: dict[str, str] = {
    "SEC-AWSACCESSKEY": """
[bold]AWS Access Key (SEC-AWSACCESSKEY)[/]

AWS Access Key IDs (beginning AKIA…) are credentials for AWS services.
Committing them exposes your account to unauthorized access, data theft,
cryptomining charges, and data exfiltration.

[bold]Why it matters:[/]
Bots scan GitHub/GitLab continuously for leaked AWS keys. Exposure time can
be seconds before a key is exploited.

[bold]How to fix:[/]
1. Rotate the key immediately in the AWS IAM console.
2. Audit CloudTrail for unauthorized usage.
3. Remove the key from git history (git filter-repo or BFG).
4. Use IAM roles, environment variables, or AWS Secrets Manager instead.
""",
    "SEC-ENV": """
[bold]Sensitive .env file committed (SEC-ENV)[/]

.env files typically contain database passwords, API keys, JWT secrets, and
other credentials. They should never be committed.

[bold]How to fix:[/]
1. Add .env to .gitignore immediately.
2. Remove it from git history.
3. Rotate all credentials contained in the file.
4. Use environment variables in CI/CD instead.
""",
    "MAP-DIST": """
[bold]Source map in distribution directory (MAP-DIST)[/]

Source maps (.map files) reverse-engineer your minified/compiled code back to
the original source. Publishing them exposes your source code to anyone who
downloads your package or opens DevTools.

[bold]How to fix:[/]
Add *.map to .npmignore or remove .map patterns from your package.json `files`.
""",
    "TEST-MISSING": """
[bold]Source changes without tests (TEST-MISSING)[/]

AI coding tools generate code quickly but often skip tests. Untested
AI-generated code is a common source of regressions, edge-case bugs, and
security gaps that only show up in production.

[bold]How to fix:[/]
Write unit tests covering the changed logic before merging. Even basic
happy-path tests catch a large percentage of AI hallucination bugs.
""",
    "RISK-EVALEXEC": """
[bold]eval() / exec() usage (RISK-EVALEXEC)[/]

Dynamic code execution functions can run arbitrary code. If user input
reaches eval/exec, this is a critical Remote Code Execution (RCE) vulnerability.

[bold]How to fix:[/]
Eliminate eval/exec if possible. If not, ensure inputs are strictly validated
and whitelisted before execution.
""",
    "AI-DISABLESECURITY": """
[bold]Security disabled (AI-DISABLESECURITY)[/]

AI coding assistants sometimes comment out or disable security controls to
make code "work" without understanding the implications. This is a very
common source of vulnerabilities in AI-generated code.

[bold]How to fix:[/]
Re-enable the security control. If the bypass is intentional, document the
reason and get a security review.
""",
}

_DEFAULT_EXPLANATION = """
[bold]{finding_id}[/]

No detailed explanation is available for this finding ID.

Run [bold]vibeguard scan --verbose[/] for inline descriptions and recommendations.
For more information, see the VibeGuard documentation:
https://github.com/dgenio/vibeguard
"""


@app.command()
def explain(
    finding_id: Annotated[str, typer.Argument(help="Finding ID to explain, e.g. SEC-ENV")],
) -> None:
    """Print an explanation of a finding type and how to fix it."""
    from vibeguard.rules.registry import RULE_REGISTRY

    c = Console()
    upper_id = finding_id.upper()

    # First try hardcoded explanations for rich output
    text = _FINDING_EXPLANATIONS.get(upper_id)
    if text:
        c.print(text)
        return

    # Then try the registry
    for metadata in RULE_REGISTRY.values():
        if upper_id in metadata.finding_ids:
            c.print(f"[bold]{upper_id}[/] — from rule [cyan]{metadata.title}[/]\n")
            c.print(f"{metadata.description}\n")
            c.print(f"[dim]Rule ID:[/] {metadata.rule_id}")
            c.print(f"[dim]Applies to:[/] {', '.join(metadata.applies_to)}")
            c.print(f"[dim]Tags:[/] {', '.join(metadata.tags)}")
            return

    err_console.print(f"[red]Unknown rule or finding ID: {finding_id}[/]")
    raise typer.Exit(2)


# ---------------------------------------------------------------------------
# rules (subcommand group)
# ---------------------------------------------------------------------------

rules_app = typer.Typer(
    name="rules",
    help="Explore available rules and their metadata.",
    no_args_is_help=True,
)
app.add_typer(rules_app, name="rules")


@rules_app.command("list")
def rules_list(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
    tag: Annotated[
        str | None,
        typer.Option("--tag", help="Filter rules by tag"),
    ] = None,
    list_plugins: Annotated[
        bool,
        typer.Option("--list-plugins", help="Include plugin information"),
    ] = False,
) -> None:
    """List all registered rules."""
    from vibeguard.rules.registry import RULE_REGISTRY

    # Ensure rules are loaded
    _ensure_rules_loaded()

    rules = list(RULE_REGISTRY.values())

    # Filter by tag
    if tag:
        tag_lower = tag.lower()
        rules = [r for r in rules if tag_lower in [t.lower() for t in r.tags]]

    if json_output:
        import json as json_mod

        payload: dict[str, object] = {
            "version": __version__,
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "title": r.title,
                    "description": r.description,
                    "finding_ids": list(r.finding_ids),
                    "default_severity": r.default_severity,
                    "confidence": r.confidence,
                    "tags": list(r.tags),
                    "applies_to": list(r.applies_to),
                }
                for r in rules
            ],
        }
        if list_plugins:
            payload["plugins"] = _get_plugins_info()
        typer.echo(json_mod.dumps(payload, indent=2))
    else:
        from rich.table import Table

        c = Console()
        table = Table(title="VibeGuard Rules")
        table.add_column("Rule ID", style="cyan", no_wrap=True)
        table.add_column("Title")
        table.add_column("Severity", style="yellow")
        table.add_column("Tags")
        for r in sorted(rules, key=lambda x: x.rule_id):
            table.add_row(r.rule_id, r.title, r.default_severity, ", ".join(r.tags))
        c.print(table)


@rules_app.command("explain")
def rules_explain(
    identifier: Annotated[str, typer.Argument(help="Rule ID or finding ID to explain")],
) -> None:
    """Explain a specific rule or finding ID."""
    from vibeguard.rules.registry import RULE_REGISTRY

    _ensure_rules_loaded()
    c = Console()
    upper_id = identifier.upper()

    # Try as rule_id first
    if identifier.lower() in RULE_REGISTRY:
        meta = RULE_REGISTRY[identifier.lower()]
        _print_rule_detail(c, meta)
        return

    # Try as finding_id
    for meta in RULE_REGISTRY.values():
        upper_finding_ids = [fid.upper() for fid in meta.finding_ids]
        if upper_id in upper_finding_ids:
            _print_rule_detail(c, meta)
            return

    err_console.print(f"[red]Unknown rule or finding ID: {identifier}[/]")
    raise typer.Exit(2)


def _print_rule_detail(c: Console, meta: Any) -> None:
    """Print detailed rule info to console."""
    c.print(f"\n[bold cyan]{meta.rule_id}[/] — [bold]{meta.title}[/]\n")
    c.print(f"{meta.description}\n")
    c.print(f"[dim]Default severity:[/] {meta.default_severity}")
    c.print(f"[dim]Confidence:[/] {meta.confidence}")
    c.print(f"[dim]Finding IDs:[/] {', '.join(meta.finding_ids)}")
    c.print(f"[dim]Tags:[/] {', '.join(meta.tags)}")
    c.print(f"[dim]Applies to:[/] {', '.join(meta.applies_to)}")
    if meta.docs_url:
        c.print(f"[dim]Documentation:[/] {meta.docs_url}")
    c.print()


def _ensure_rules_loaded() -> None:
    """Import all rule modules to ensure they register themselves."""
    from vibeguard.rules.registry import RULE_REGISTRY

    if RULE_REGISTRY:
        return
    # Import all rule modules to trigger registration
    import importlib
    import pkgutil

    import vibeguard.rules as rules_pkg

    for _importer, modname, _ispkg in pkgutil.iter_modules(rules_pkg.__path__):
        if modname == "__init__" or modname == "registry":
            continue
        with contextlib.suppress(Exception):
            importlib.import_module(f"vibeguard.rules.{modname}")


def _get_plugins_info() -> dict[str, list[str]]:
    """Get info about loaded/failed plugins."""
    loaded: list[str] = []
    failed: list[str] = []
    try:
        from importlib.metadata import entry_points

        eps = entry_points()
        if hasattr(eps, "select"):
            plugin_eps = eps.select(group="vibeguard.plugins")
        else:
            plugin_eps = eps.get("vibeguard.plugins", [])  # type: ignore[arg-type]
        for ep in plugin_eps:
            try:
                ep.load()
                loaded.append(ep.name)
            except Exception:
                failed.append(ep.name)
    except Exception:
        pass
    return {"loaded": loaded, "failed": failed}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_path(path: Path) -> None:
    """Validate that the scan path exists and is a directory."""
    if not path.exists():
        err_console.print(f"[red]Error: path does not exist: {path}[/]")
        raise typer.Exit(2)
    if path.is_file():
        err_console.print(
            f"[red]Error: path is a file, not a directory: {path}[/]\n"
            "Hint: pass the parent directory instead."
        )
        raise typer.Exit(2)


def _load_config(config_path: Path | None, scan_path: Path) -> VibeGuardConfig:
    """Load config, searching scan_path if no explicit config given."""
    if config_path:
        try:
            return VibeGuardConfig.load(config_path)
        except ValidationError as exc:
            err_console.print(f"[red]Invalid config {config_path}:[/]")
            for error in exc.errors():
                loc = " → ".join(str(p) for p in error["loc"])
                err_console.print(f"  [bold]{loc}[/]: {error['msg']}")
            raise typer.Exit(2) from exc
        except Exception as exc:
            err_console.print(f"[red]Error loading config {config_path}: {exc}[/]")
            raise typer.Exit(2) from exc

    # Auto-discover vibeguard.yaml in scan path
    candidate = scan_path / "vibeguard.yaml"
    if candidate.exists():
        try:
            return VibeGuardConfig.load(candidate)
        except ValidationError as exc:
            err_console.print(f"[red]Invalid config {candidate}:[/]")
            for error in exc.errors():
                loc = " → ".join(str(p) for p in error["loc"])
                err_console.print(f"  [bold]{loc}[/]: {error['msg']}")
            raise typer.Exit(2) from exc
        except Exception as exc:
            err_console.print(f"[yellow]⚠ Could not load {candidate}: {exc}. Using defaults.[/]")

    return VibeGuardConfig()


def _parse_severity(value: str) -> Severity:
    valid = [s.value for s in Severity]
    try:
        return Severity(value.lower())
    except ValueError:
        err_console.print(f"[red]Invalid severity: {value!r}. Valid options: {', '.join(valid)}[/]")
        raise typer.Exit(2) from None
