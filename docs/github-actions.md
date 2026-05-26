# GitHub Actions Adoption Guide

This guide shows how to integrate VibeGuard into your GitHub Actions PR workflow using SARIF code scanning, PR comments, baselines, and annotations.

## 1. Minimal PR Gate Workflow

The simplest setup: fail PRs that introduce high/critical findings.

```yaml
name: VibeGuard Gate
on:
  pull_request:

permissions:
  contents: read

jobs:
  vibeguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # needed for --diff mode

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - name: Install VibeGuard
        run: pip install vibeguard-gate

      - name: Run VibeGuard gate
        run: vibeguard gate --diff --fail-on high
```

Or using the first-party action:

```yaml
      - uses: dgenio/vibeguard@v0.7
        with:
          diff: 'true'
          fail-on: high
```

## 2. SARIF Upload (Code Scanning Annotations)

Upload SARIF to get inline annotations in PR diffs and findings in the Security tab.

```yaml
name: VibeGuard Code Scanning
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  security-events: write  # required for SARIF upload

jobs:
  vibeguard-sarif:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - name: Install VibeGuard
        run: pip install vibeguard-gate

      - name: Run VibeGuard scan (SARIF)
        run: vibeguard scan --sarif > vibeguard.sarif
        continue-on-error: true

      - name: Upload SARIF to Code Scanning
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: vibeguard.sarif
          category: vibeguard
```

## 3. PR Comment Workflow

Post a formatted summary comment on each PR.

```yaml
name: VibeGuard PR Comment
on:
  pull_request:

permissions:
  contents: read
  pull-requests: write  # required for posting comments

jobs:
  vibeguard-comment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - name: Install VibeGuard
        run: pip install vibeguard-gate

      - name: Generate PR comment
        run: vibeguard gate --diff --fail-on high --pr-comment > vibeguard-comment.md
        continue-on-error: true

      - name: Post comment
        run: gh pr comment ${{ github.event.pull_request.number }} --body-file vibeguard-comment.md
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## 4. Baseline Workflow

Create a baseline on the default branch to suppress pre-existing findings, then use it in PRs.

### Create baseline on main branch merges:

```yaml
name: Update VibeGuard Baseline
on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  update-baseline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip

      - name: Install VibeGuard
        run: pip install vibeguard-gate

      - name: Create baseline
        run: vibeguard baseline create --output .vibeguard-baseline.json

      - name: Commit baseline
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add .vibeguard-baseline.json
          git diff --cached --quiet || git commit -m "chore: update vibeguard baseline"
          git push
```

### Use baseline in PR gate:

```yaml
      - name: Run gate with baseline
        run: vibeguard gate --diff --fail-on high --baseline .vibeguard-baseline.json
```

## 5. Recommended Thresholds

| Risk Profile | `fail-on` | Use Case |
|---|---|---|
| **Strict** | `medium` | Regulated environments, security-critical code |
| **Balanced** | `high` | Default for most teams |
| **Audit-only** | `critical` | Initial adoption, observability mode |
| **Info** | — (don't gate) | Use `scan` instead of `gate` for monitoring |

## 6. Caching

Speed up runs by caching pip installs:

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: '**/pyproject.toml'
```

## Problem Matcher

VibeGuard ships a [problem matcher](../.github/problem-matchers/vibeguard.json) for console output.
Enable it to get annotations even without `--sarif`:

```yaml
      - name: Enable VibeGuard problem matcher
        run: echo "::add-matcher::.github/problem-matchers/vibeguard.json"
```

## Annotations Mode

VibeGuard auto-emits `::error`, `::warning`, and `::notice` annotations when running inside GitHub Actions. Disable with `--no-annotations`:

```yaml
      - name: Run without annotations
        run: vibeguard gate --diff --fail-on high --no-annotations
```
