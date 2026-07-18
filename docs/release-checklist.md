# Release Checklist

VibeGuard's adoption depends on trust, and version drift quietly erodes it:
if `pyproject.toml`, PyPI, the GitHub release, the action snippet in the
README, and the plugin examples disagree, the tool looks experimental even
when the code is solid. This checklist keeps those surfaces aligned and
prevents the drift class tracked in #86, #87, and #94 from recurring.

---

## Canonical version source

There is exactly **one** source of truth for the package version:

> **`pyproject.toml` → `[project].version`**

Everything else derives from it:

- `vibeguard.__version__` is **not** hardcoded — it reads the installed
  distribution metadata via `importlib.metadata` (the package
  `vibeguard-gate`), so it always equals the `pyproject.toml` version of the
  installed build. `tests/test_docs_references.py::TestVersionSource` fails
  if anyone reverts it to a hardcoded literal (which previously drifted —
  `0.8.0` in code vs `0.8.1` in `pyproject.toml`). Because the version comes
  from installed metadata, run `make install-dev` before `make docs` /
  `make check-versions` in a fresh checkout — otherwise `__version__` falls
  back to the `0.0.0+unknown` source-tree sentinel and `docs/rules.md`
  regenerates with it.
- The PyPI release is built from this version.
- The GitHub release tag is `v<version>` (e.g. `0.8.1` → `v0.8.1`).

Two version-like surfaces are **independent** of the package version on
purpose:

- **`PLUGIN_API_VERSION`** (in `vibeguard/__init__.py`) tracks the *plugin
  API* contract, not the release. It only changes on a plugin-API break.
  See [`plugin-api.md`](plugin-api.md).
- **The GitHub Action tag** referenced in docs (`dgenio/vibeguard@v<version>`)
  tracks the latest *action* release. It can legitimately lag the PyPI patch
  version — you do not have to cut a new action tag for every patch — but all
  copies of the snippet must reference the **same** tag at any given time.

## PyPI vs GitHub Action — which to document

VibeGuard ships two adoption paths; keep their docs distinct and current:

- **PyPI (`pip install vibeguard-gate`)** — the canonical way to run
  VibeGuard locally, in pre-commit, or in a hand-written CI step. The README
  Quickstart and GitHub Actions "pip install" snippet use this.
- **First-party GitHub Action (`uses: dgenio/vibeguard@v<version>`)** — the
  lowest-friction PR-gate path. The README's top-of-page snippet, plus
  [`github-actions.md`](github-actions.md) and
  [`github-action-reference.md`](github-action-reference.md), use this.

When in doubt, point new users at the **GitHub Action** for PR gating and at
**PyPI** for local/CLI use.

---

## Release steps

### 1. Pre-flight (on a release branch)

- [ ] `make ci` is green (`lint`, `format-check`, `typecheck`, `docs-check`,
      `test`).
- [ ] `make check-versions` passes (no doc/version drift — see below).
- [ ] `make docs` produces no diff (`docs/rules.md` is current).
- [ ] Self-scan is clean: `vibeguard gate --path . --fail-on critical`.

### 2. Bump the version

- [ ] Update `[project].version` in `pyproject.toml`.
- [ ] If any **stable** surface changed incompatibly, this is a **major**
      bump — see the [stability contract](stability-contract.md) for what
      counts as breaking, and write the migration note now.
- [ ] If a detection change can newly-block a previously-passing gate, prefer
      a **minor** bump and note it in the release notes.

### 3. Update the docs that reference a version

- [ ] If cutting a new **action** release, bump every `dgenio/vibeguard@v<version>`
      snippet to the new tag (README + `docs/`). They must all match; this is
      what `make check-versions` enforces.
- [ ] Confirm the plugin pin examples in [`plugin-api.md`](plugin-api.md)
      still use an API-tracking lower bound (`vibeguard-gate>=X.Y`) with no
      upper bound that excludes the new release.
- [ ] Confirm the README install instruction is `pip install vibeguard-gate`.

### 4. Tag, publish, release

- [ ] Tag the commit: `git tag v<version> && git push origin v<version>`.
- [ ] Publish to PyPI (the `publish` workflow builds from the tag).
- [ ] Create the GitHub release for `v<version>` with notes that:
  - summarise user-visible changes;
  - call out any **breaking** changes and migration steps;
  - link the [stability contract](stability-contract.md);
  - call out detection changes that can change a gate result.
- [ ] If you cut a new action tag, move/update any rolling major tag you
      maintain (e.g. `v1`) to point at it.

### 5. Post-release verification

- [ ] `pip install vibeguard-gate==<version>` from a clean environment works.
- [ ] The action snippet in the README resolves to a real, published tag.
- [ ] `make check-versions` still passes on `main`.

---

## Automated drift guard

`scripts/check_doc_versions.py` is the mechanical backstop for this
checklist. It validates, without contacting the network:

- every `dgenio/vibeguard@v<version>` reference across the README, `docs/`,
  `action.yml`, and `.github/workflows/` pins the **same** tag (no silent
  drift between copies);
- plugin pin examples (`vibeguard-gate>=…`) use an open-ended,
  API-tracking lower bound rather than an upper bound that would exclude the
  current release (the #86 failure mode);
- the README documents the canonical PyPI install (`pip install
  vibeguard-gate`).

Run it directly or via make:

```bash
python scripts/check_doc_versions.py     # exit 1 on drift
make check-versions
```

It is also enforced in CI by
`tests/test_docs_references.py::TestDocVersionCheck`, alongside the existing
action-tag-existence guard (`TestGitHubActionDocs`), so this checklist cannot
quietly rot.

## Pinned GitHub Actions

All third-party actions in `.github/workflows/*.yml` and in `action.yml` are
pinned to full commit SHAs with a trailing `# vX.Y.Z` comment (#190). The
`github-actions` entry in `.github/dependabot.yml` keeps those pins fresh —
Dependabot bumps the SHA and the version comment together.

One set of pins is **not** covered by Dependabot: the workflow template that
`vibeguard setup github-actions` generates lives as a string literal in
`vibeguard/ci_setup.py`. Dependabot cannot see it, so when preparing a release,
refresh those SHAs by hand if the pinned actions (`actions/checkout`,
`actions/setup-python`, `github/codeql-action`, `actions/github-script`) have cut
new releases. Resolve the SHA for a tag with
`git ls-remote https://github.com/<owner>/<repo> <tag>`.
