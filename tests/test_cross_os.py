"""Cross-OS determinism guards (#167).

VibeGuard is path- and console-encoding heavy and is run locally on Windows and
macOS as much as in Linux CI. These tests pin the OS-sensitive contracts so the
Windows/macOS legs of the CI matrix have something concrete to catch:

* finding ``path`` values are always ``/``-separated (SARIF- and
  fingerprint-portable), never backslash-separated, on every OS;
* a baseline created on one OS suppresses the same finding on another, because
  fingerprints depend only on the normalized posix path;
* console rendering does not crash under a legacy (cp1252-like) console encoding
  that cannot represent the severity glyphs.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from vibeguard.baseline import (
    compute_fingerprint,
    create_baseline,
    filter_baselined,
)
from vibeguard.config import VibeGuardConfig
from vibeguard.models import Confidence, Finding, ScanResult, Severity
from vibeguard.reporters.console import _harden_console_encoding, build_findings_table
from vibeguard.scanner import run_scan

# A well-known example AWS key that deterministically fires SEC-AWSACCESSKEY.
_AWS_EXAMPLE_KEY = "AKIAIOSFODNN7EXAMPLE"


def _make_finding(path: str) -> Finding:
    return Finding(
        id="SEC-ENV",
        rule="secrets",
        title="Test finding",
        description="d",
        severity=Severity.CRITICAL,
        path=path,
        line=3,
        evidence="x",
        recommendation="fix",
        tags=["t"],
        confidence=Confidence.HIGH,
    )


class TestPosixFindingPaths:
    """Finding paths must be ``/``-separated on every OS (stability contract)."""

    def test_nested_finding_paths_are_posix(self, tmp_path: Path):
        nested = tmp_path / "pkg" / "sub"
        nested.mkdir(parents=True)
        (nested / "secret.py").write_text(f'key = "{_AWS_EXAMPLE_KEY}"\n')

        result = run_scan(tmp_path, VibeGuardConfig())
        paths = [f.path for f in result.findings]
        assert paths, "expected the example AWS key to produce a finding"

        for p in paths:
            # On Windows, os.sep is '\\'; a finding path that leaked it would
            # break SARIF consumers and make fingerprints non-portable.
            assert "\\" not in p, f"finding path is not posix-normalized: {p!r}"
            assert not Path(p).is_absolute(), f"finding path should be repo-relative: {p!r}"

        assert any(p == "pkg/sub/secret.py" for p in paths), (
            f"expected the nested posix path 'pkg/sub/secret.py' in {paths!r}"
        )


class TestCrossOsBaseline:
    """A baseline made on one OS must suppress the same finding on another."""

    def test_fingerprint_is_separator_stable(self):
        # A Windows-style backslash path and its POSIX form must fingerprint
        # identically: Finding normalizes separators at the model boundary (#167),
        # so a baseline created on one OS suppresses the same finding on another.
        assert compute_fingerprint(_make_finding("pkg\\sub\\secret.py")) == compute_fingerprint(
            _make_finding("pkg/sub/secret.py")
        )
        # Distinct files still fingerprint differently.
        assert compute_fingerprint(_make_finding("pkg/sub/a.py")) != compute_fingerprint(
            _make_finding("pkg/sub/b.py")
        )

    def test_backslash_path_is_normalized_on_the_model(self):
        # The normalization is on Finding itself, so it holds on every OS and for
        # every rule/reporter — not only where the scanner builds the path.
        assert _make_finding("pkg\\sub\\secret.py").path == "pkg/sub/secret.py"

    def test_nested_findings_round_trip_through_baseline(self, tmp_path: Path):
        nested = tmp_path / "pkg" / "sub"
        nested.mkdir(parents=True)
        (nested / "secret.py").write_text(f'key = "{_AWS_EXAMPLE_KEY}"\n')

        config = VibeGuardConfig()
        result = run_scan(tmp_path, config)
        assert result.findings, "expected a finding to baseline"

        baseline = create_baseline(result.findings)
        # Baseline entries store the posix path verbatim, so they are portable.
        for entry in baseline.entries.values():
            assert "\\" not in entry.path

        # Re-scan and confirm every previously-seen finding is suppressed —
        # the same outcome a Linux baseline would produce against a Windows scan.
        rescan = run_scan(tmp_path, config)
        assert filter_baselined(rescan.findings, baseline) == []


class TestConsoleEncoding:
    """Legacy console encodings must degrade glyphs, not crash the report (#167)."""

    def _cp1252_console(self) -> tuple[Console, io.BytesIO]:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        return Console(file=stream, width=80), raw

    def _result(self) -> ScanResult:
        return ScanResult(findings=[_make_finding("src/a.py")], scanned_files=1, policy="balanced")

    def test_unhardened_cp1252_console_would_crash(self):
        # Proves the fix is load-bearing: without hardening, the skull glyph
        # (U+2620) raises on a strict cp1252 stream.
        console, _ = self._cp1252_console()
        with pytest.raises(UnicodeEncodeError):
            console.print(build_findings_table(self._result()))
            console.file.flush()

    def test_hardened_cp1252_console_does_not_crash(self):
        console, raw = self._cp1252_console()
        _harden_console_encoding(console)
        # Must not raise, and must still emit output.
        console.print(build_findings_table(self._result()))
        console.file.flush()
        assert raw.getvalue(), "hardened console produced no output"

    def test_utf8_console_is_left_untouched(self):
        # The common case: a UTF-8 console encodes the glyphs fine and keeps them.
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="utf-8", errors="strict")
        console = Console(file=stream, width=80)
        _harden_console_encoding(console)
        console.print(build_findings_table(self._result()))
        console.file.flush()
        assert "☠".encode() in raw.getvalue(), "UTF-8 console should keep the severity glyph"
