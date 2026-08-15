"""Documentation contract for the normative Trustworthy Observe threat model (#232)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


# These tests intentionally pin the navigation/review surfaces required by the
# #232 acceptance criteria so a later docs cleanup cannot silently orphan the
# normative security contract.
def test_threat_model_is_linked_from_required_surfaces() -> None:
    assert "docs/threat-model.md" in _text("README.md")
    assert "docs/threat-model.md" in _text("SECURITY.md")
    assert "threat-model.md" in _text("docs/stability-contract.md")
    assert "docs/threat-model.md" in _text("CONTRIBUTING.md")


def test_contributor_guidance_requires_security_boundary_review() -> None:
    contributing = " ".join(_text("CONTRIBUTING.md").split())
    for term in (
        "scope resolution",
        "policy/configuration",
        "suppressions",
        "baselines",
        "plugin trust",
        "execution/completeness status",
        "evidence/report semantics",
        "CI integration/permissions",
    ):
        assert term in contributing


def test_threat_model_keeps_no_findings_non_certification_boundary() -> None:
    threat_model = _text("docs/threat-model.md").lower()
    assert "no findings does not mean no vulnerabilities" in threat_model
    assert "continuation does not certify a change as secure" in threat_model
