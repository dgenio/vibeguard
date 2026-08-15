"""Governance regressions for inline suppression semantics (#132)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibeguard.config import VibeGuardConfig
from vibeguard.scanner import run_scan
from vibeguard.suppressions import parse_inline_suppressions


@pytest.mark.parametrize(
    "directive",
    [
        "# vibeguard: ignore SEC-AWSACCESSKEY",
        '# vibeguard: ignore SEC-AWSACCESSKEY reason=""',
        '# vibeguard: ignore SEC-AWSACCESSKEY reason="   "',
    ],
)
def test_reasonless_directive_is_not_a_suppression(directive: str) -> None:
    assert parse_inline_suppressions(directive) == {}


@pytest.mark.parametrize(
    "directive",
    [
        "# vibeguard: ignore SEC-AWSACCESSKEY",
        '# vibeguard: ignore SEC-AWSACCESSKEY reason=""',
        '# vibeguard: ignore SEC-AWSACCESSKEY reason="   "',
    ],
)
def test_reasonless_directive_preserves_original_finding(tmp_path: Path, directive: str) -> None:
    source = f'{directive}\nAWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
    (tmp_path / "config.py").write_text(source, encoding="utf-8")

    result = run_scan(tmp_path, VibeGuardConfig())
    ids = [finding.id for finding in result.findings]

    assert "SEC-AWSACCESSKEY" in ids
    assert "SUPPRESSION-NO-REASON" in ids


def test_reasoned_directive_remains_effective(tmp_path: Path) -> None:
    source = (
        '# vibeguard: ignore SEC-AWSACCESSKEY reason="intentional test fixture"\n'
        'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
    )
    (tmp_path / "config.py").write_text(source, encoding="utf-8")

    result = run_scan(tmp_path, VibeGuardConfig())
    ids = [finding.id for finding in result.findings]

    assert "SEC-AWSACCESSKEY" not in ids
    assert "SUPPRESSION-NO-REASON" not in ids
