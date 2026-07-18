"""Tests guarding against stale documentation references.

These are mechanical "did the docs drift again?" checks that catch the exact
paper-cut patterns called out in the v1 newcomer-audit issues:

- #86: `docs/plugin-api.md` had a `vibeguard-gate>=0.6,<0.7` pin that
  excluded the current release.
- #87: `docs/github-action-reference.md` / `docs/github-actions.md` referenced
  `dgenio/vibeguard@v0.2`, a tag that never existed.
- #91: `CONTRIBUTING.md` told contributors to wait for PR #74 to land — but
  PR #74 had been merged for weeks.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
README = REPO_ROOT / "README.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
COMPARISON = DOCS_DIR / "comparison.md"
VERSION_CHECK = REPO_ROOT / "scripts" / "check_doc_versions.py"

# Snapshot of published tags as a fallback when the test runs outside a git
# checkout (e.g. an installed sdist). The live source of truth — used when
# available — is ``git tag -l`` in the working tree; see ``_known_tags``.
_FALLBACK_TAGS = frozenset({"v0.1.1", "v0.4.0", "v0.5.0", "v0.6.0", "v0.7.0", "v0.8.0"})


def _known_tags() -> frozenset[str]:
    """Return the set of tags that GitHub will resolve for ``dgenio/vibeguard@<ref>``.

    Prefer ``git tag -l`` so the set tracks the repo on every release without
    a manual list update — that hand-maintained list was the same staleness
    class issue #87 was filed to prevent. Fall back to a snapshot when git is
    not available (e.g. installed sdist).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "tag", "-l"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return _FALLBACK_TAGS
    tags = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return frozenset(tags) if tags else _FALLBACK_TAGS


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _github_slug(heading_text: str) -> str:
    """Approximate GitHub's heading-anchor slug: lowercase, drop punctuation
    GitHub strips (keeping word chars, spaces, hyphens), spaces -> hyphens."""
    text = re.sub(r"[^\w\s-]", "", heading_text.strip().lower())
    return text.replace(" ", "-")


def _markdown_heading_slugs(text: str) -> set[str]:
    """Collect anchor slugs for every ATX heading, ignoring fenced code blocks
    so `# comment` lines inside ```` ``` ```` snippets are not treated as headings."""
    slugs: set[str] = set()
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"#{1,6}\s+(.*)", line)
        if match:
            slugs.add(_github_slug(match.group(1)))
    return slugs


class TestPluginApiDocs:
    """Issue #86: plugin pin must include the current release."""

    def test_pin_does_not_exclude_current_release(self):
        text = _read(DOCS_DIR / "plugin-api.md")
        # The historical broken pin must be gone.
        assert ">=0.6,<0.7" not in text, (
            "docs/plugin-api.md still pins vibeguard-gate>=0.6,<0.7 — "
            "that range excludes the current release. See #86."
        )

    def test_pin_mentions_plugin_api_version(self):
        """The replacement prose must teach plugin authors to track
        PLUGIN_API_VERSION (the contract that's stable) rather than the
        release version (which moves every few weeks)."""
        text = _read(DOCS_DIR / "plugin-api.md")
        assert "PLUGIN_API_VERSION" in text


class TestGitHubActionDocs:
    """Issue #87: every `dgenio/vibeguard@<ref>` in docs must resolve."""

    _ACTION_REF = re.compile(r"dgenio/vibeguard@(v[\w.]+)")

    def test_all_action_refs_are_real_tags(self):
        offenders: list[tuple[Path, str]] = []
        # Sweep docs (.md) and the top-level action manifest (action.yml)
        # together — both surface the same `dgenio/vibeguard@<tag>` ref to
        # newcomers and both have shipped with stale references before.
        candidate_paths: list[Path] = list(DOCS_DIR.rglob("*.md"))
        candidate_paths.append(REPO_ROOT / "action.yml")
        candidate_paths.append(REPO_ROOT / "README.md")
        known_tags = _known_tags()
        for path in candidate_paths:
            if not path.exists():
                continue
            for ref in self._ACTION_REF.findall(_read(path)):
                if ref not in known_tags:
                    offenders.append((path.relative_to(REPO_ROOT), ref))
        assert not offenders, (
            "Files reference dgenio/vibeguard@<tag> for tag(s) that do not "
            f"exist: {offenders}. Update the file to a real tag, or cut the "
            f"tag before merging. See #87."
        )

    def test_action_ref_tag_is_consistent_across_docs(self):
        """The PR-gate snippet is duplicated in README and docs/comparison.md
        (#95/#96). Markdown can't transclude, so guard that both copies pin the
        same `dgenio/vibeguard@<tag>` and can't silently drift apart."""
        refs: set[str] = set()
        for path in (README, COMPARISON):
            if path.exists():
                refs.update(self._ACTION_REF.findall(_read(path)))
        assert len(refs) <= 1, (
            "README and docs/comparison.md pin different dgenio/vibeguard "
            f"action tags: {sorted(refs)}. The duplicated PR-gate snippets must "
            "stay on one tag so they can't drift apart."
        )


class TestContributingNoStaleIssueRefs:
    """Issue #91: CONTRIBUTING.md must not tell readers to wait for a PR
    that has long since merged."""

    def test_no_pending_pr_references_in_contributing(self):
        text = _read(REPO_ROOT / "CONTRIBUTING.md")
        # The exact patterns the audit flagged. Both must be gone.
        assert "once PR #74 lands" not in text
        assert "until PR #" not in text.lower()

    def test_contributing_points_at_how_to_add_a_rule(self):
        """The doc that PR #74 shipped — make sure CONTRIBUTING actually
        sends people to it now."""
        text = _read(REPO_ROOT / "CONTRIBUTING.md")
        assert "docs/how-to-add-a-rule.md" in text

    def test_rule_wiring_mentions_both_locations(self):
        """The Adding-a-new-rule section must mention both wiring sites,
        not just `vibeguard/scanner.py` — see #91's second paragraph."""
        text = _read(REPO_ROOT / "CONTRIBUTING.md")
        assert "vibeguard/scanner.py" in text
        assert "load_all_builtin_rules" in text


class TestComparisonGuide:
    """Issue #96: a dedicated comparison guide must exist, be linked from the
    README, frame VibeGuard as complementary (not a replacement), and cover
    each tool category the issue calls out."""

    def test_comparison_guide_exists(self):
        assert COMPARISON.exists(), "docs/comparison.md is missing — see #96."

    def test_readme_links_to_comparison_guide(self):
        assert "docs/comparison.md" in _read(README), (
            "README must link to docs/comparison.md so readers can find the "
            "per-tool breakdown. See #96."
        )

    def test_guide_covers_every_tool_category(self):
        assert COMPARISON.exists(), "docs/comparison.md is missing — see #96."
        text = _read(COMPARISON)
        # The five categories the issue enumerates must each be present.
        for tool in ("CodeQL", "Semgrep", "gitleaks", "Dependabot", "eslint"):
            assert tool in text, f"docs/comparison.md does not mention {tool!r} — see #96."

    def test_guide_frames_vibeguard_as_complementary(self):
        """The guide must say VibeGuard complements rather than replaces, and
        must keep the explicit 'do not use as' boundary the issue asks for."""
        assert COMPARISON.exists(), "docs/comparison.md is missing — see #96."
        text = _read(COMPARISON)
        assert "complement" in text.lower()
        assert "Use VibeGuard when" in text
        assert "Do not use VibeGuard as" in text


class TestAdoptionReadme:
    """Issue #95: the README must surface an adoption-first path — a one-line
    positioning statement plus a GitHub Actions PR-gate snippet — near the top,
    above the deep CLI reference."""

    def test_readme_has_positioning_statement(self):
        assert "deterministic pre-merge safety gate for AI-generated diffs" in _read(README), (
            "README is missing the one-line positioning statement. See #95."
        )

    def test_action_snippet_appears_before_cli_reference(self):
        """The copy-paste GitHub Actions gate must be above the fold — i.e.
        before the deep `## CLI Reference` section — so a reader sees the
        adoption path without scrolling the whole README."""
        text = _read(README)
        gate_idx = text.find("dgenio/vibeguard@")
        cli_idx = text.find("## CLI Reference")
        assert gate_idx != -1, "README has no GitHub Action snippet — see #95."
        assert cli_idx != -1, "README is missing its CLI Reference section."
        assert gate_idx < cli_idx, (
            "The GitHub Actions gate snippet must appear before the CLI "
            "reference so the adoption path is above the fold. See #95."
        )


class TestEcosystemNote:
    """Issue #104: the README must explain where VibeGuard fits in a broader
    ecosystem while making clear it remains fully standalone."""

    def test_readme_has_ecosystem_section(self):
        assert "## Ecosystem" in _read(README), "README is missing the ## Ecosystem note. See #104."

    def test_ecosystem_note_states_standalone(self):
        text = _read(README)
        _, sep, ecosystem = text.partition("## Ecosystem")
        assert sep, "README is missing the ## Ecosystem note. See #104."
        assert "standalone" in ecosystem.lower(), (
            "The ecosystem note must state that VibeGuard is fully standalone. See #104."
        )


class TestReadmeAnchors:
    """Issue #95: the adoption-first section links in-page anchors (e.g. the
    30-second demo and example output). Guard that every intra-doc anchor link
    in the README resolves to a real heading, so a future heading rename can't
    silently break the adoption funnel's navigation."""

    def test_intradoc_anchor_links_resolve(self):
        text = _read(README)
        slugs = _markdown_heading_slugs(text)
        broken = sorted(
            anchor for anchor in re.findall(r"\]\(#([^)]+)\)", text) if anchor not in slugs
        )
        assert not broken, (
            f"README links to in-page anchor(s) with no matching heading: {broken}. "
            "Rename the link or restore the heading. See #95."
        )


class TestStabilityContract:
    """Issue #102: a v1 stability contract must exist, be linked from the
    README, distinguish `scan` from `gate`, and cover the stable surfaces."""

    CONTRACT = DOCS_DIR / "stability-contract.md"

    def test_contract_exists(self):
        assert self.CONTRACT.exists(), "docs/stability-contract.md is missing — see #102."

    def test_readme_links_to_contract(self):
        assert "docs/stability-contract.md" in _read(README), (
            "README must link to docs/stability-contract.md. See #102."
        )

    def test_contract_distinguishes_scan_from_gate(self):
        text = _read(self.CONTRACT)
        assert "scan" in text and "gate" in text
        # The core promise: scan never fails the build; gate is the CI gate.
        assert "always exits `0`" in text, (
            "The contract must state that `scan` always exits 0 (informational). See #102."
        )

    def test_contract_covers_stable_surfaces(self):
        text = _read(self.CONTRACT)
        for topic in (
            "Exit code",
            "Finding ID",
            "config",
            "SARIF",
            "Plugin API",
            "Versioning policy",
        ):
            assert topic in text, f"stability contract does not cover {topic!r} — see #102."

    def test_contract_documents_fail_closed_behaviour(self):
        """The acceptance criteria require the documented operational behaviour
        to match the tests that guarantee it (#81/#83/#82)."""
        text = _read(self.CONTRACT)
        assert "fail" in text.lower() and "exit `2`" in text
        assert "test_cli_e2e.py" in text, (
            "The contract should cite the tests that back its fail-closed "
            "guarantees so docs and behaviour stay in sync. See #102."
        )


class TestRoadmap:
    """Issue #101: a roadmap must exist, be linked from README and
    CONTRIBUTING, and document the contribution funnel."""

    ROADMAP = DOCS_DIR / "roadmap.md"

    def test_roadmap_exists(self):
        assert self.ROADMAP.exists(), "docs/roadmap.md is missing — see #101."

    def test_readme_links_to_roadmap(self):
        assert "docs/roadmap.md" in _read(README), "README must link to docs/roadmap.md. See #101."

    def test_contributing_links_to_roadmap(self):
        assert "docs/roadmap.md" in _read(CONTRIBUTING), (
            "CONTRIBUTING.md must link to docs/roadmap.md. See #101."
        )

    def test_roadmap_has_now_next_later_nongoals(self):
        text = _read(self.ROADMAP).lower()
        for section in ("now", "next", "later", "non-goal"):
            assert section in text, f"roadmap is missing a {section!r} section — see #101."

    def test_roadmap_documents_label_taxonomy(self):
        text = _read(self.ROADMAP)
        # The evidence-first taxonomy (#170): priority, status, and evidence
        # labels must all be documented so contributors can read the funnel.
        assert "priority:p0" in text
        assert "status:blocked" in text
        assert "status:maintenance" in text
        assert "needs-evidence" in text

    def test_roadmap_distinguishes_core_from_plugin(self):
        text = _read(self.ROADMAP).lower()
        assert "plugin" in text and "core" in text


class TestReleaseChecklist:
    """Issue #94: a release checklist must exist, name a single canonical
    version source, and document the PyPI vs GitHub Action paths."""

    CHECKLIST = DOCS_DIR / "release-checklist.md"

    def test_checklist_exists(self):
        assert self.CHECKLIST.exists(), "docs/release-checklist.md is missing — see #94."

    def test_readme_links_to_checklist(self):
        assert "docs/release-checklist.md" in _read(README), (
            "README must link to docs/release-checklist.md. See #94."
        )

    def test_checklist_names_canonical_version_source(self):
        text = _read(self.CHECKLIST)
        assert "pyproject.toml" in text and "version" in text.lower()

    def test_checklist_documents_pypi_and_action_paths(self):
        text = _read(self.CHECKLIST)
        assert "pip install vibeguard-gate" in text
        assert "dgenio/vibeguard@" in text

    def test_checklist_references_drift_guard(self):
        assert "check_doc_versions" in _read(self.CHECKLIST), (
            "The checklist should point at the automated drift guard. See #94."
        )


class TestVersionSource:
    """Issue #94: there is one canonical version source. ``__version__`` must
    derive from the installed distribution metadata (pyproject.toml), never a
    hardcoded literal that can silently drift (it shipped as 0.8.0 while
    pyproject was 0.8.1)."""

    INIT = REPO_ROOT / "vibeguard" / "__init__.py"

    def test_version_is_not_hardcoded(self):
        text = _read(self.INIT)
        assert "importlib.metadata" in text, (
            "vibeguard/__init__.py must derive __version__ from "
            "importlib.metadata, not hardcode it. See #94."
        )
        # Catch a hardcoded release literal (e.g. "0.8.0") while allowing the
        # "0.0.0+unknown" source-checkout sentinel — the closing quote must
        # follow the x.y.z, which the +unknown sentinel does not have.
        assert not re.search(r'__version__\s*=\s*[\'"]\d+\.\d+\.\d+[\'"]', text), (
            "vibeguard/__init__.py hardcodes a release __version__; derive it "
            "from package metadata so it tracks pyproject.toml. See #94."
        )

    def test_version_matches_distribution_metadata(self):
        from importlib.metadata import version

        import vibeguard

        assert vibeguard.__version__ == version("vibeguard-gate")


class TestDocVersionCheck:
    """Issue #94: the version-drift guard script must pass on the current tree
    and must actually catch drift (so it is a real gate, not a no-op)."""

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERSION_CHECK), *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_script_exists(self):
        assert VERSION_CHECK.exists(), "scripts/check_doc_versions.py is missing — see #94."

    def test_passes_on_current_repo(self):
        result = self._run()
        assert result.returncode == 0, result.stderr

    def test_detects_action_tag_drift(self, tmp_path: Path):
        (tmp_path / "README.md").write_text(
            "pip install vibeguard-gate\nuses: dgenio/vibeguard@v0.8.0\n", encoding="utf-8"
        )
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "actions.md").write_text(
            "uses: dgenio/vibeguard@v0.7.0\n", encoding="utf-8"
        )
        result = self._run("--root", str(tmp_path))
        assert result.returncode == 1
        assert "disagree" in result.stderr

    def test_detects_excluding_plugin_pin(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("pip install vibeguard-gate\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "plugin.md").write_text(
            'dependencies = ["vibeguard-gate>=0.6,<0.7"]\n', encoding="utf-8"
        )
        result = self._run("--root", str(tmp_path))
        assert result.returncode == 1
        assert "upper" in result.stderr

    def test_detects_missing_install_instruction(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("no install line here\n", encoding="utf-8")
        result = self._run("--root", str(tmp_path))
        assert result.returncode == 1
        assert "pip install vibeguard-gate" in result.stderr


class TestWeaverStackReadme:
    """Issue #119: the README must carry a standardized 'Part of the Weaver
    Stack' block while keeping the standalone / no-telemetry promise explicit,
    without diluting the existing Ecosystem section."""

    def test_readme_has_weaver_stack_section(self):
        assert "## Part of the Weaver Stack" in _read(README), (
            "README is missing the 'Part of the Weaver Stack' block. See #119."
        )

    def test_block_preserves_standalone_promise(self):
        text = _read(README)
        _, sep, block = text.partition("## Part of the Weaver Stack")
        assert sep, "README is missing the Weaver Stack block. See #119."
        # Stop at the next top-level heading so we only inspect this block.
        block = block.split("\n## ", 1)[0]
        assert "standalone" in block.lower()
        assert "no runtime dependency" in block.lower()
        assert "never phones home" in block.lower()

    def test_block_mentions_topic_and_siblings(self):
        text = _read(README)
        _, _, block = text.partition("## Part of the Weaver Stack")
        block = block.split("\n## ", 1)[0]
        assert "weaver-stack" in block, (
            "the block must name the shared `weaver-stack` topic. See #119."
        )
        for sibling in ("agentfence", "lessonweaver", "weaver-spec"):
            assert sibling in block, (
                f"the block should position VibeGuard next to {sibling}. See #119."
            )

    def test_existing_ecosystem_section_still_present(self):
        # The new block must not replace the Ecosystem note guarded by #104.
        assert "## Ecosystem" in _read(README)


class TestInteropLessonsDoc:
    """Issues #103/#120: the interop design note must exist, be linked from the
    README, document the ArtifactSafetyReport export and the LessonCard
    outcome, distinguish one-off from repeated, and keep the no-runtime-
    dependency promise."""

    DOC = DOCS_DIR / "interop-lessons.md"
    EXAMPLE = REPO_ROOT / "examples" / "interop" / "findings_to_lessons.py"
    REPORT_SCHEMA = DOCS_DIR / "weaver" / "artifact_safety_report.schema.json"
    LESSON_SCHEMA = DOCS_DIR / "weaver" / "lesson_card.schema.json"

    def test_doc_exists(self):
        assert self.DOC.exists(), "docs/interop-lessons.md is missing — see #103/#120."

    def test_readme_links_to_doc(self):
        assert "docs/interop-lessons.md" in _read(README), (
            "README must link to docs/interop-lessons.md. See #103/#120."
        )

    def test_doc_documents_export_and_lesson_contracts(self):
        text = _read(self.DOC)
        assert "ArtifactSafetyReport" in text
        assert "LessonCard" in text
        assert "--weaver" in text

    def test_doc_distinguishes_one_off_from_repeated(self):
        text = _read(self.DOC).lower()
        assert "one-off" in text and "repeated" in text

    def test_doc_states_no_runtime_dependency(self):
        text = _read(self.DOC).lower()
        assert "no runtime dependency" in text
        assert "optional" in text

    def test_vendored_schemas_exist_and_are_valid_json(self):
        import json

        for schema_path in (self.REPORT_SCHEMA, self.LESSON_SCHEMA):
            assert schema_path.exists(), f"{schema_path} is missing — see #120."
            data = json.loads(schema_path.read_text())
            # Preserve the upstream contract identity for diffing against spec.
            assert "weaver-spec.dev" in data["$id"]

    def test_runnable_example_exists(self):
        assert self.EXAMPLE.exists(), (
            "examples/interop/findings_to_lessons.py is missing — see #103."
        )
