"""End-to-end CLI tests against bundled example packages."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vibeguard.cli import app

runner = CliRunner()
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


class TestGateDiffBaseFlag:
    """`--base` for diff mode (#208), end-to-end through the CLI."""

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        if shutil.which("git") is None:
            pytest.skip("git not installed")
        root = tmp_path / "repo"
        root.mkdir()
        _git(root, "init", "-q", "-b", "trunk")
        _git(root, "config", "user.email", "t@example.com")
        _git(root, "config", "user.name", "t")
        (root / "app.py").write_text("x = 1\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "init")
        # A feature branch with a benign change off the non-default base.
        _git(root, "checkout", "-q", "-b", "feature")
        (root / "app.py").write_text("x = 1\ny = 2\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "edit")
        return root

    def test_diff_with_non_default_base_runs(self, repo: Path):
        result = runner.invoke(app, ["gate", "--path", str(repo), "--diff", "--base", "trunk"])
        # Benign change → gate passes (exit 0); the point is that an explicit
        # non-main base resolves and is used without falling back/erroring.
        assert result.exit_code == 0

    def test_invalid_base_surfaces_warning_not_silent(self, repo: Path):
        result = runner.invoke(
            app, ["scan", "--path", str(repo), "--diff", "--base", "origin/nope"]
        )
        assert result.exit_code == 0  # scan is informational
        assert "origin/nope" in result.output


class TestScanE2ENodePackage:
    """E2E tests scanning the vulnerable-node-package example."""

    pkg_path = str(EXAMPLES_DIR / "vulnerable-node-package")

    def test_scan_exits_zero(self):
        result = runner.invoke(app, ["scan", "--path", self.pkg_path])
        assert result.exit_code == 0

    def test_scan_json_schema(self):
        result = runner.invoke(app, ["scan", "--path", self.pkg_path, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "findings" in data
        assert "scanned_files" in data
        assert "policy" in data
        assert isinstance(data["findings"], list)

    def test_scan_json_has_findings(self):
        result = runner.invoke(app, ["scan", "--path", self.pkg_path, "--json"])
        data = json.loads(result.stdout)
        assert len(data["findings"]) > 0
        # Each finding has required fields
        for f in data["findings"]:
            assert "id" in f
            assert "severity" in f
            assert "path" in f
            assert "title" in f

    def test_scan_markdown_output(self):
        result = runner.invoke(app, ["scan", "--path", self.pkg_path, "--markdown"])
        assert result.exit_code == 0
        assert "VibeGuard" in result.stdout
        assert "finding" in result.stdout.lower() or "|" in result.stdout

    def test_gate_fails_on_high(self):
        result = runner.invoke(app, ["gate", "--path", self.pkg_path, "--fail-on", "high"])
        assert result.exit_code == 1

    def test_gate_fails_on_critical(self):
        """Gate with --fail-on critical fails because the fixture has critical findings."""
        result = runner.invoke(app, ["gate", "--path", self.pkg_path, "--fail-on", "critical"])
        assert result.exit_code == 1


class TestScanE2EPythonPackage:
    """E2E tests scanning the vulnerable-python-package example."""

    pkg_path = str(EXAMPLES_DIR / "vulnerable-python-package")

    def test_scan_exits_zero(self):
        result = runner.invoke(app, ["scan", "--path", self.pkg_path])
        assert result.exit_code == 0

    def test_scan_json_has_findings(self):
        result = runner.invoke(app, ["scan", "--path", self.pkg_path, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data["findings"]) > 0

    def test_gate_fails_on_high(self):
        result = runner.invoke(app, ["gate", "--path", self.pkg_path, "--fail-on", "high"])
        assert result.exit_code == 1


class TestVersionCommand:
    """Tests for the version subcommand (#12)."""

    def test_version_subcommand_output(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "vibeguard" in result.stdout.lower()
        assert "Python" in result.stdout
        assert "Platform" in result.stdout
        assert "Install path" in result.stdout

    def test_version_flag_still_works(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "vibeguard" in result.stdout.lower()


class TestValidateCommand:
    """Tests for the validate subcommand (#14)."""

    def test_validate_valid_config(self, tmp_path: Path):
        cfg = tmp_path / "vibeguard.yaml"
        cfg.write_text("policy: strict\nfail_on: medium\n")
        result = runner.invoke(app, ["validate", "--config", str(cfg)])
        assert result.exit_code == 0

    def test_validate_invalid_config_extra_field(self, tmp_path: Path):
        cfg = tmp_path / "vibeguard.yaml"
        cfg.write_text("policy: strict\nfail_oon: high\n")
        result = runner.invoke(app, ["validate", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "fail_oon" in result.stdout or "fail_oon" in (result.stderr or "")

    def test_validate_missing_file(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "--config", str(tmp_path / "nope.yaml")])
        assert result.exit_code == 1

    def test_validate_discovers_in_path(self, tmp_path: Path):
        cfg = tmp_path / "vibeguard.yaml"
        cfg.write_text("policy: balanced\nfail_on: high\n")
        result = runner.invoke(app, ["validate", "--path", str(tmp_path)])
        assert result.exit_code == 0


class TestMutualExclusionOutput:
    """Tests for mutually exclusive --json/--markdown (#15)."""

    def test_scan_json_and_markdown_fails(self, tmp_path: Path):
        (tmp_path / "f.py").write_text("x = 1\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--json", "--markdown"])
        assert result.exit_code == 2

    def test_gate_json_and_markdown_fails(self, tmp_path: Path):
        (tmp_path / "f.py").write_text("x = 1\n")
        result = runner.invoke(
            app,
            ["gate", "--path", str(tmp_path), "--json", "--markdown", "--fail-on", "high"],
        )
        assert result.exit_code == 2

    def test_scan_invalid_fail_on(self, tmp_path: Path):
        (tmp_path / "f.py").write_text("x = 1\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--fail-on", "disaster"])
        assert result.exit_code == 2


class TestMalformedConfigErrorContext:
    """A malformed config must exit 2 and name the underlying cause (#183)."""

    def test_invalid_config_value_reports_cause_and_exits_2(self, tmp_path: Path):
        # `policy` only accepts relaxed/balanced/strict; an unknown value is a
        # validation error whose detail should reach the operator.
        (tmp_path / "vibeguard.yaml").write_text("policy: chaotic\n")
        (tmp_path / "f.py").write_text("x = 1\n")
        result = runner.invoke(app, ["gate", "--path", str(tmp_path), "--fail-on", "high"])
        assert result.exit_code == 2
        combined = result.stdout + (result.stderr or "")
        assert "Invalid config" in combined
        # The pydantic detail (the offending key) must be surfaced, not swallowed.
        assert "policy" in combined


class TestPathValidation:
    """Scan targets must fail closed on a missing input (#81, #83).

    Since #213, an explicitly named *file* is a valid target (scanned directly)
    rather than rejected; the #83 guarantee — never silently scan 0 files — is
    preserved by scanning the file. Git-backed modes (`--diff`/`--staged`) still
    require a directory.
    """

    def test_gate_missing_path_fails_closed(self):
        result = runner.invoke(app, ["gate", "--path", "/does/not/exist", "--fail-on", "high"])
        assert result.exit_code == 2
        combined = result.stdout + (result.stderr or "")
        # The gate must NOT report success on a bad path.
        assert "Gate passed" not in combined
        assert "does not exist" in combined

    def test_scan_missing_path_errors(self):
        result = runner.invoke(app, ["scan", "--path", "/does/not/exist"])
        assert result.exit_code == 2
        assert "does not exist" in result.stdout + (result.stderr or "")

    def test_scan_file_path_is_scanned(self):
        """#213: a single file target is scanned directly, never silently 0."""
        env_file = EXAMPLES_DIR / "vulnerable-node-package" / ".env"
        result = runner.invoke(app, ["scan", "--path", str(env_file), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["scanned_files"] == 1
        assert "must be a directory" not in result.stdout + (result.stderr or "")

    def test_diff_file_path_rejected(self):
        """Git-backed modes still require a directory, not a file (#83)."""
        env_file = EXAMPLES_DIR / "vulnerable-node-package" / ".env"
        result = runner.invoke(app, ["gate", "--path", str(env_file), "--diff"])
        assert result.exit_code == 2
        assert "must be a directory" in result.stdout + (result.stderr or "")

    def test_publish_check_missing_path_errors(self):
        result = runner.invoke(app, ["publish-check", "--path", "/does/not/exist"])
        assert result.exit_code == 2
        assert "does not exist" in result.stdout + (result.stderr or "")

    def test_baseline_create_missing_path_errors(self, tmp_path: Path):
        result = runner.invoke(
            app,
            [
                "baseline",
                "create",
                "--path",
                "/does/not/exist",
                "--output",
                str(tmp_path / "b.json"),
            ],
        )
        assert result.exit_code == 2
        assert "does not exist" in result.stdout + (result.stderr or "")

    def test_baseline_update_missing_path_errors(self, tmp_path: Path):
        result = runner.invoke(
            app,
            [
                "baseline",
                "update",
                "--path",
                "/does/not/exist",
                "--output",
                str(tmp_path / "b.json"),
            ],
        )
        assert result.exit_code == 2
        assert "does not exist" in result.stdout + (result.stderr or "")

    def test_valid_directory_still_scans(self, tmp_path: Path):
        (tmp_path / "app.py").write_text("print('hi')\n")
        result = runner.invoke(app, ["gate", "--path", str(tmp_path), "--fail-on", "high"])
        assert result.exit_code == 0


class TestScanFailOnHelp:
    """`scan --fail-on` help must not claim it exits non-zero (#84)."""

    def test_fail_on_help_matches_informational_behavior(self):
        result = runner.invoke(app, ["scan", "--help"])
        assert result.exit_code == 0
        # Collapse wrapping so phrase checks are robust to terminal width.
        normalized = " ".join((result.stdout + (result.stderr or "")).split())
        assert "Exit non-zero" not in normalized
        assert "exits 0" in normalized
        assert "gate" in normalized


class TestBinarySafety:
    """Tests for binary/large file safety (#16)."""

    def test_binary_file_does_not_crash(self, tmp_path: Path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        (tmp_path / "app.py").write_text("print('hello')\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # Binary file should be skipped
        assert any("binary" in e for e in data.get("errors", []))

    def test_large_file_skipped(self, tmp_path: Path):
        cfg = tmp_path / "vibeguard.yaml"
        cfg.write_text("scanner:\n  max_file_size_kb: 1\n")
        (tmp_path / "big.py").write_text("x = 1\n" * 500)  # > 1 KB
        (tmp_path / "small.py").write_text("x = 1\n")
        result = runner.invoke(
            app, ["scan", "--path", str(tmp_path), "--json", "--config", str(cfg)]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # big.py should be skipped due to size
        assert any("big.py" in e for e in data.get("errors", []))


class TestVibeguardIgnore:
    """Tests for .vibeguardignore support (#26)."""

    def test_ignorefile_excludes_matched_files(self, tmp_path: Path):
        (tmp_path / ".vibeguardignore").write_text("secret_dir/\n")
        secret_dir = tmp_path / "secret_dir"
        secret_dir.mkdir()
        (secret_dir / "leak.py").write_text('key = "AKIAIOSFODNN7EXAMPLE"\n')
        (tmp_path / "safe.py").write_text("x = 1\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # The secret in secret_dir should not produce findings
        finding_paths = [f["path"] for f in data["findings"]]
        assert not any("secret_dir" in p for p in finding_paths)

    def test_ignorefile_comments_ignored(self, tmp_path: Path):
        (tmp_path / ".vibeguardignore").write_text("# comment\n*.log\n")
        (tmp_path / "debug.log").write_text("some log\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # .log file should be excluded, .vibeguardignore and app.py counted
        finding_paths = [f["path"] for f in data["findings"]]
        assert not any("debug.log" in p for p in finding_paths)


class TestOutputAndReport:
    """`--output` / `--report` file destinations (#233)."""

    pkg_path = str(EXAMPLES_DIR / "vulnerable-node-package")

    def test_output_writes_sarif_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "vibeguard.sarif"
        result = runner.invoke(
            app, ["scan", "--path", self.pkg_path, "--sarif", "--output", str(dest)]
        )
        assert result.exit_code == 0
        data = json.loads(dest.read_text(encoding="utf-8"))
        assert data["version"] == "2.1.0"
        # stdout must not also carry the SARIF (it went to the file).
        assert "$schema" not in result.stdout

    def test_output_json_byte_identical_to_stdout(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.json"
        runner.invoke(app, ["scan", "--path", self.pkg_path, "--json", "--output", str(dest)])
        stdout_result = runner.invoke(app, ["scan", "--path", self.pkg_path, "--json"])
        # File content equals stdout (modulo the single trailing newline echo adds).
        assert dest.read_text(encoding="utf-8").rstrip("\n") == stdout_result.stdout.rstrip("\n")

    def test_output_dash_means_stdout(self) -> None:
        result = runner.invoke(app, ["scan", "--path", self.pkg_path, "--json", "--output", "-"])
        assert result.exit_code == 0
        assert json.loads(result.stdout)["findings"] is not None

    def test_output_without_format_flag_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["scan", "--path", self.pkg_path, "--output", str(tmp_path / "x")]
        )
        assert result.exit_code == 2

    def test_output_unwritable_path_fails_closed(self, tmp_path: Path) -> None:
        bad = tmp_path / "nonexistent-dir" / "out.json"
        result = runner.invoke(
            app, ["scan", "--path", self.pkg_path, "--json", "--output", str(bad)]
        )
        assert result.exit_code == 2

    def test_report_multi_format_single_scan(self, tmp_path: Path) -> None:
        sarif = tmp_path / "vg.sarif"
        comment = tmp_path / "comment.md"
        result = runner.invoke(
            app,
            [
                "gate",
                "--path",
                self.pkg_path,
                "--fail-on",
                "high",
                "--report",
                f"sarif={sarif}",
                "--report",
                f"pr-comment={comment}",
            ],
        )
        # gate still enforces (the node package has high findings).
        assert result.exit_code == 1
        assert json.loads(sarif.read_text(encoding="utf-8"))["version"] == "2.1.0"
        assert "VibeGuard" in comment.read_text(encoding="utf-8")

    def test_report_rejects_bad_spec(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["scan", "--path", self.pkg_path, "--report", "sarif"])
        assert result.exit_code == 2

    def test_report_rejects_unknown_format(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["scan", "--path", self.pkg_path, "--report", f"bogus={tmp_path / 'x'}"]
        )
        assert result.exit_code == 2

    def test_report_cannot_mix_with_format_flag(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["scan", "--path", self.pkg_path, "--json", "--report", f"sarif={tmp_path / 'x'}"],
        )
        assert result.exit_code == 2

    def test_publish_check_output_to_file(self, tmp_path: Path) -> None:
        runner.invoke(
            app,
            [
                "publish-check",
                "--path",
                str(EXAMPLES_DIR / "vulnerable-node-package"),
                "--json",
                "--output",
                str(tmp_path / "pub.json"),
            ],
        )
        # exit code depends on findings; the file must be valid JSON regardless.
        assert (tmp_path / "pub.json").exists()
        data = json.loads((tmp_path / "pub.json").read_text(encoding="utf-8"))
        assert "manifest" in data and "result" in data
