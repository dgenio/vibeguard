"""Tests for `vibeguard setup github-actions` (#99) and its PR-gate wiring (#116)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from vibeguard.ci_setup import (
    CONFIG_REL,
    WORKFLOW_REL,
    SetupError,
    render_workflow,
    resolve_fail_on,
    setup_github_actions,
)
from vibeguard.cli import app
from vibeguard.reporters.markdown import PR_COMMENT_MARKER

runner = CliRunner()


class TestRenderWorkflow:
    def test_threshold_substituted(self):
        wf = render_workflow("medium")
        assert "--fail-on medium --pr-comment" in wf
        assert "__FAIL_ON__" not in wf

    def test_marker_matches_reporter(self):
        # The upsert script must look for the exact marker the reporter emits,
        # or the comment will be duplicated on every push instead of updated.
        wf = render_workflow("high")
        assert f'const marker = "{PR_COMMENT_MARKER}";' in wf
        assert "__MARKER__" not in wf

    def test_upsert_paginates_and_filters_to_bot_author(self):
        # The upsert must page through all comments (listComments caps at 30) so
        # the marker comment is found on long PRs, and must only match the
        # github-actions[bot] author so a user echoing the marker can't hijack it.
        wf = render_workflow("high")
        assert "github.paginate(github.rest.issues.listComments" in wf
        assert "per_page: 100" in wf
        assert 'c.user?.login === "github-actions[bot]"' in wf

    def test_docs_upsert_matches_generated_workflow(self):
        # The docs/github-actions.md Section 3 example is a hand-maintained twin
        # of the generated upsert. Pin the load-bearing lines to both so the docs
        # copy can't silently drift (the original pagination bug existed in both).
        docs = (Path(__file__).parent.parent / "docs" / "github-actions.md").read_text(
            encoding="utf-8"
        )
        for line in (
            "github.paginate(github.rest.issues.listComments",
            "per_page: 100",
            'c.user?.login === "github-actions[bot]"',
        ):
            assert line in render_workflow("high"), f"missing in generated workflow: {line}"
            assert line in docs, f"missing in docs/github-actions.md: {line}"

    def test_workflow_is_valid_yaml_with_expected_surfaces(self):
        doc = yaml.safe_load(render_workflow("high"))
        # `on:` parses to the boolean True under YAML 1.1; GitHub's own parser
        # handles the literal `on:` fine. Assert via the round-tripped key.
        assert doc["permissions"] == {
            "contents": "read",
            "pull-requests": "write",
            "security-events": "write",
        }
        steps = doc["jobs"]["vibeguard"]["steps"]
        uses = [s.get("uses", "") for s in steps]
        assert any(u.startswith("github/codeql-action/upload-sarif") for u in uses)
        assert any(u.startswith("actions/github-script") for u in uses)

    def test_passes_pr_base_ref(self):
        # The generated workflow pins --diff to the PR's target branch (#208) so
        # diff scoping matches the merge base instead of relying on detection.
        wf = render_workflow("high")
        assert '--base "origin/${{ github.base_ref }}"' in wf
        # Both the SARIF scan and the gate step thread the base ref.
        assert wf.count('--base "origin/${{ github.base_ref }}"') == 2

    def test_no_action_tag_ref(self):
        # Generated workflow installs from PyPI so it never pins a
        # dgenio/vibeguard@vX.Y.Z tag that check_doc_versions.py would police.
        wf = render_workflow("high")
        assert "pip install vibeguard-gate" in wf
        assert "dgenio/vibeguard@" not in wf

    def test_third_party_actions_are_sha_pinned(self):
        # #190: every third-party action in the generated workflow must be pinned
        # to a full 40-char commit SHA with a trailing version comment, never a
        # floating tag/branch ref — the same standard VibeGuard's own workflows
        # hold, and what `vibeguard setup github-actions --dry-run` should emit.
        wf = render_workflow("high")
        uses_refs = re.findall(r"uses:\s*(\S+)", wf)
        assert uses_refs, "expected the generated workflow to use at least one action"

        sha_pinned = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
        floating = re.compile(r"@(v[0-9]|main|master|release/)")
        for ref in uses_refs:
            assert sha_pinned.match(ref), f"action is not SHA-pinned: {ref!r}"
            assert not floating.search(ref), f"action uses a floating ref: {ref!r}"

        # Each pinned line carries a human-readable version comment.
        for line in wf.splitlines():
            if "uses:" in line and "@" in line:
                assert re.search(r"#\s*v\d", line), f"SHA pin missing version comment: {line!r}"


class TestResolveFailOn:
    def test_explicit_flag_wins(self):
        assert resolve_fail_on("critical", {"fail_on": "medium"}) == "critical"

    def test_pack_value_used_when_no_flag(self):
        assert resolve_fail_on(None, {"fail_on": "medium"}) == "medium"

    def test_default_high_without_flag_or_pack(self):
        assert resolve_fail_on(None, None) == "high"

    def test_invalid_flag_raises(self):
        try:
            resolve_fail_on("bogus", None)
        except SetupError:
            return
        raise AssertionError("expected SetupError for invalid --fail-on")


class TestSetupGithubActions:
    def test_creates_workflow(self, tmp_path: Path):
        result = setup_github_actions(root=tmp_path)
        assert (tmp_path / WORKFLOW_REL).exists()
        assert result.created == [tmp_path / WORKFLOW_REL]
        assert not (tmp_path / CONFIG_REL).exists()

    def test_with_config_also_writes_config(self, tmp_path: Path):
        setup_github_actions(root=tmp_path, with_config=True)
        assert (tmp_path / CONFIG_REL).exists()

    def test_policy_pack_writes_config_and_derives_threshold(self, tmp_path: Path):
        setup_github_actions(root=tmp_path, policy_pack="web-app")
        config = (tmp_path / CONFIG_REL).read_text()
        assert "policy_pack: web-app" in config
        # web-app pins fail_on: medium, so the workflow must gate on medium.
        assert "--fail-on medium" in (tmp_path / WORKFLOW_REL).read_text()

    def test_refuses_existing_without_force(self, tmp_path: Path):
        (tmp_path / WORKFLOW_REL).parent.mkdir(parents=True)
        (tmp_path / WORKFLOW_REL).write_text("name: existing\n")
        try:
            setup_github_actions(root=tmp_path)
        except SetupError as exc:
            assert "Refusing to overwrite" in str(exc)
            assert (tmp_path / WORKFLOW_REL).read_text() == "name: existing\n"
            return
        raise AssertionError("expected SetupError when target exists")

    def test_force_overwrites(self, tmp_path: Path):
        (tmp_path / WORKFLOW_REL).parent.mkdir(parents=True)
        (tmp_path / WORKFLOW_REL).write_text("name: existing\n")
        setup_github_actions(root=tmp_path, force=True)
        assert "name: VibeGuard" in (tmp_path / WORKFLOW_REL).read_text()

    def test_dry_run_writes_nothing(self, tmp_path: Path):
        result = setup_github_actions(root=tmp_path, with_config=True, dry_run=True)
        assert not (tmp_path / WORKFLOW_REL).exists()
        assert not (tmp_path / CONFIG_REL).exists()
        # ...but it still renders the would-be content for inspection.
        assert (tmp_path / WORKFLOW_REL) in result.rendered
        assert (tmp_path / CONFIG_REL) in result.rendered

    def test_unknown_pack_raises(self, tmp_path: Path):
        try:
            setup_github_actions(root=tmp_path, policy_pack="nope")
        except SetupError as exc:
            assert "Unknown policy pack" in str(exc)
            return
        raise AssertionError("expected SetupError for unknown pack")


class TestSetupCLI:
    def test_cli_creates_workflow(self, tmp_path: Path):
        result = runner.invoke(app, ["setup", "github-actions", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / WORKFLOW_REL).exists()

    def test_cli_dry_run_prints_yaml_and_writes_nothing(self, tmp_path: Path):
        result = runner.invoke(
            app, ["setup", "github-actions", "--path", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "name: VibeGuard" in result.stdout
        assert not (tmp_path / WORKFLOW_REL).exists()

    def test_cli_existing_file_exits_two(self, tmp_path: Path):
        (tmp_path / WORKFLOW_REL).parent.mkdir(parents=True)
        (tmp_path / WORKFLOW_REL).write_text("name: existing\n")
        result = runner.invoke(app, ["setup", "github-actions", "--path", str(tmp_path)])
        assert result.exit_code == 2

    def test_cli_invalid_fail_on_exits_two(self, tmp_path: Path):
        result = runner.invoke(
            app, ["setup", "github-actions", "--path", str(tmp_path), "--fail-on", "bogus"]
        )
        assert result.exit_code == 2
