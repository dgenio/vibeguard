"""Tests for CLI exit codes and commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vibeguard.cli import app

runner = CliRunner()


class TestCLIInit:
    def test_init_creates_config(self, tmp_path: Path):
        result = runner.invoke(app, ["init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "vibeguard.yaml").exists()

    def test_init_skips_existing(self, tmp_path: Path):
        (tmp_path / "vibeguard.yaml").write_text("policy: relaxed\n")
        result = runner.invoke(app, ["init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        # Content should not be overwritten
        assert (tmp_path / "vibeguard.yaml").read_text() == "policy: relaxed\n"


class TestCLIScan:
    def test_scan_clean_dir_exits_zero(self, tmp_path: Path):
        (tmp_path / "hello.py").write_text("print('hello')\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path)])
        assert result.exit_code == 0

    def test_scan_json_output(self, tmp_path: Path):
        (tmp_path / "hello.py").write_text("print('hello')\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "findings" in data

    def test_scan_markdown_output(self, tmp_path: Path):
        (tmp_path / "hello.py").write_text("print('hello')\n")
        result = runner.invoke(app, ["scan", "--path", str(tmp_path), "--markdown"])
        assert result.exit_code == 0
        assert "VibeGuard" in result.stdout

    def test_scan_always_exits_zero(self, tmp_path: Path):
        """scan command should exit 0 even with findings."""
        (tmp_path / "secret.py").write_text('token = "ghp_' + "A" * 36 + '"\n')
        result = runner.invoke(app, ["scan", "--path", str(tmp_path)])
        assert result.exit_code == 0


class TestCLIGate:
    def test_gate_clean_dir_exits_zero(self, tmp_path: Path):
        (tmp_path / "hello.py").write_text("print('hello')\n")
        result = runner.invoke(app, ["gate", "--path", str(tmp_path), "--fail-on", "high"])
        assert result.exit_code == 0

    def test_gate_with_critical_finding_exits_one(self, tmp_path: Path):
        (tmp_path / "secret.py").write_text('key = "AKIAIOSFODNN7EXAMPLE"\n')
        result = runner.invoke(
            app,
            ["gate", "--path", str(tmp_path), "--fail-on", "high"],
        )
        assert result.exit_code == 1

    def test_gate_fail_on_low_exits_one_on_info(self, tmp_path: Path):
        """Gate with --fail-on low should fail when any non-info finding exists."""
        (tmp_path / "app.js.map").write_text('{"version":3}')
        result = runner.invoke(
            app,
            ["gate", "--path", str(tmp_path), "--fail-on", "low"],
        )
        assert result.exit_code == 1


class TestCLIExplain:
    def test_explain_known_id(self):
        result = runner.invoke(app, ["explain", "SEC-ENV"])
        assert result.exit_code == 0
        assert len(result.stdout) > 10

    def test_explain_unknown_id(self):
        result = runner.invoke(app, ["explain", "NOTREAL-999"])
        assert result.exit_code == 2  # Unknown ID exits non-zero


class TestCLIVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "vibeguard" in result.stdout.lower()
