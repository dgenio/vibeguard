"""Tests for repo-level metadata: issue forms, PR template, and CONTRIBUTING.

These guard against silent rot in the `.github/` issue/PR templates and the
contributor-facing markdown — for example, a renamed rule that leaves a stale
dropdown option, or a CONTRIBUTING file whose install command drifts from
`pyproject.toml`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

import vibeguard.scanner  # noqa: F401  # ensures RULE_REGISTRY is populated
from vibeguard.rules.registry import RULE_REGISTRY

REPO_ROOT = Path(__file__).resolve().parent.parent
ISSUE_TEMPLATE_DIR = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
PR_TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
README = REPO_ROOT / "README.md"

ISSUE_FORM_FILES = [
    "bug_report.yml",
    "feature_request.yml",
    "rule_request.yml",
    "false_positive_report.yml",
]

# YAML issue-form body types we expect to see. Anything else likely indicates
# a typo or use of an unsupported field.
ALLOWED_BODY_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}


class TestIssueFormConfig:
    def test_config_yml_exists_and_parses(self):
        config = ISSUE_TEMPLATE_DIR / "config.yml"
        assert config.exists(), "Missing .github/ISSUE_TEMPLATE/config.yml"
        data = yaml.safe_load(config.read_text(encoding="utf-8"))
        assert data["blank_issues_enabled"] is False
        contact = data["contact_links"]
        assert isinstance(contact, list)
        assert any("security" in link["name"].lower() for link in contact), (
            "config.yml should include a security contact link"
        )


@pytest.mark.parametrize("filename", ISSUE_FORM_FILES)
class TestIssueForms:
    """One copy of each check per issue-form file."""

    def _load(self, filename: str) -> dict:
        path = ISSUE_TEMPLATE_DIR / filename
        assert path.exists(), f"Missing .github/ISSUE_TEMPLATE/{filename}"
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_top_level_fields(self, filename: str):
        data = self._load(filename)
        assert isinstance(data.get("name"), str) and data["name"].strip()
        assert isinstance(data.get("description"), str) and data["description"].strip()
        assert isinstance(data.get("body"), list) and len(data["body"]) >= 1

    def test_body_types_are_valid(self, filename: str):
        data = self._load(filename)
        for i, item in enumerate(data["body"]):
            assert isinstance(item, dict), f"body[{i}] in {filename} must be a mapping"
            kind = item.get("type")
            assert kind in ALLOWED_BODY_TYPES, (
                f"body[{i}].type={kind!r} in {filename} is not a recognized "
                f"issue-form type; expected one of {sorted(ALLOWED_BODY_TYPES)}"
            )

    def test_form_has_a_checklist(self, filename: str):
        data = self._load(filename)
        kinds = [item.get("type") for item in data["body"]]
        assert "checkboxes" in kinds, (
            f"{filename} should end with a `checkboxes` block (de-dup confirmation, etc.)"
        )


class TestRuleDropdownsReferenceRealRules:
    """Dropdown options that list rule_ids must match RULE_REGISTRY exactly.

    This catches the most common rot: someone renames a rule_id in
    vibeguard/rules/*.py and forgets that two issue forms hard-code the same
    list of options.
    """

    @pytest.mark.parametrize(
        ("filename", "dropdown_label_fragment"),
        [
            ("rule_request.yml", "related existing rule"),
            ("false_positive_report.yml", "rule that fired"),
        ],
    )
    def test_dropdown_options_match_registry(self, filename: str, dropdown_label_fragment: str):
        data = yaml.safe_load((ISSUE_TEMPLATE_DIR / filename).read_text(encoding="utf-8"))
        dropdowns = [
            item
            for item in data["body"]
            if item.get("type") == "dropdown"
            and dropdown_label_fragment.lower()
            in (item.get("attributes", {}).get("label", "")).lower()
        ]
        assert len(dropdowns) == 1, (
            f"{filename} should have exactly one dropdown labelled "
            f"~{dropdown_label_fragment!r}; found {len(dropdowns)}"
        )

        options = dropdowns[0]["attributes"]["options"]
        # Strip the "new rule (none of the above)" escape hatch, if present.
        rule_options = {opt for opt in options if not opt.lower().startswith("new rule")}
        registered = set(RULE_REGISTRY.keys())

        missing_from_form = registered - rule_options
        extra_in_form = rule_options - registered
        assert not missing_from_form, (
            f"{filename}: rule_ids in RULE_REGISTRY missing from the dropdown "
            f"options: {sorted(missing_from_form)}"
        )
        assert not extra_in_form, (
            f"{filename}: dropdown lists rule_ids that are not in RULE_REGISTRY: "
            f"{sorted(extra_in_form)}"
        )

    def test_false_positive_finding_id_placeholder_is_real(self):
        """The example finding-id placeholder must correspond to a real rule.

        If a finding ID is renamed in the registry, the issue-form placeholder
        will mislead reporters until updated. This test catches that drift.
        """
        data = yaml.safe_load(
            (ISSUE_TEMPLATE_DIR / "false_positive_report.yml").read_text(encoding="utf-8")
        )
        finding_id_inputs = [
            item
            for item in data["body"]
            if item.get("type") == "input" and item.get("id") == "finding-id"
        ]
        assert len(finding_id_inputs) == 1, (
            "false_positive_report.yml should have exactly one input id=finding-id"
        )
        placeholder = finding_id_inputs[0]["attributes"].get("placeholder", "").strip()
        assert placeholder, "finding-id input must have a non-empty placeholder"

        all_finding_ids = {fid for rule in RULE_REGISTRY.values() for fid in rule.finding_ids}
        assert placeholder in all_finding_ids, (
            f"false_positive_report.yml placeholder {placeholder!r} is not a real finding ID; "
            f"either update the placeholder or update the renamed rule"
        )


class TestPullRequestTemplate:
    def test_exists_and_non_empty(self):
        assert PR_TEMPLATE.exists()
        body = PR_TEMPLATE.read_text(encoding="utf-8")
        assert len(body.strip()) > 100

    def test_references_closes_keyword(self):
        body = PR_TEMPLATE.read_text(encoding="utf-8")
        assert "Closes #" in body, "PR template should prompt for `Closes #<issue>`"

    def test_lists_verification_commands(self):
        """The template asks contributors to run the same checks CI runs."""
        body = PR_TEMPLATE.read_text(encoding="utf-8")
        for needle in ("pytest", "ruff check", "ruff format", "mypy", "vibeguard gate"):
            assert needle in body, f"PR template should mention `{needle}`"


class TestContributingDoc:
    def test_exists_and_non_empty(self):
        assert CONTRIBUTING.exists()
        body = CONTRIBUTING.read_text(encoding="utf-8")
        assert len(body.strip()) > 500

    def test_install_command_matches_pyproject(self):
        """Avoid recommending an install command that doesn't actually work."""
        body = CONTRIBUTING.read_text(encoding="utf-8")
        assert "python -m pip install -e . --group dev" in body
        assert 'pip install -e ".[dev]"' not in body

    def test_lists_core_dev_commands(self):
        body = CONTRIBUTING.read_text(encoding="utf-8")
        for needle in ("pytest", "ruff check", "ruff format", "mypy", "vibeguard gate"):
            assert needle in body, f"CONTRIBUTING.md should mention `{needle}`"

    def test_links_security_and_license(self):
        body = CONTRIBUTING.read_text(encoding="utf-8")
        assert "SECURITY.md" in body
        assert "LICENSE" in body


class TestReadmeQuickReference:
    """Light sanity checks on the README that guard the documented contract."""

    def test_quick_reference_lists_every_registered_rule(self):
        body = README.read_text(encoding="utf-8")
        for rule_id in RULE_REGISTRY:
            assert f"`{rule_id}`" in body, f"README rule quick-reference is missing `{rule_id}`"

    def test_links_to_contributing(self):
        body = README.read_text(encoding="utf-8")
        assert "CONTRIBUTING.md" in body

    def test_source_install_uses_dev_group(self):
        """The contributor-oriented source quickstart must install maintainer tooling."""
        body = README.read_text(encoding="utf-8")
        assert "python -m pip install -e . --group dev" in body
        assert 'pip install -e ".[dev]"' not in body

    def test_install_command_uses_published_name(self):
        """The PyPI distribution name is `vibeguard-gate`, not `vibeguard`."""
        body = README.read_text(encoding="utf-8")
        assert "pip install vibeguard-gate" in body
        # The bare `pip install vibeguard` form (i.e. not followed by `-gate`)
        # silently installs the wrong package — guard against it reappearing.
        # The pattern catches the most common installer invocations
        # (pip, pip3, `python -m pip`, `python3 -m pip`); the negative
        # lookahead permits `vibeguard-gate` with any suffix
        # (e.g. `==0.6.0`, `[extra]`, trailing whitespace).
        bare_form = re.compile(r"\b(?:pip3?|python3?\s+-m\s+pip)\s+install\s+vibeguard\b(?!-gate)")
        bad_lines = [line for line in body.splitlines() if bare_form.search(line.strip())]
        assert not bad_lines, (
            "README has a literal `pip install vibeguard` line (should be `vibeguard-gate`): "
            f"{bad_lines!r}"
        )
