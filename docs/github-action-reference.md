# VibeGuard GitHub Action

The `dgenio/vibeguard` action runs VibeGuard as a composite GitHub Action step.

## Usage

```yaml
- uses: dgenio/vibeguard@v0.7
  with:
    path: '.'
    diff: 'true'
    fail-on: 'high'
    output-format: 'sarif'
    output-file: 'vibeguard.sarif'
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `path` | No | `.` | Directory to scan |
| `config` | No | `` | Path to vibeguard.yaml |
| `diff` | No | `false` | Scan only changed files |
| `fail-on` | No | `high` | Severity threshold for gate failure |
| `output-format` | No | `console` | `console`, `json`, `markdown`, `sarif`, `annotations`, `diagnostics`, `pr-comment` |
| `output-file` | No | `` | Write output to this file path |
| `baseline` | No | `` | Path to baseline file |
| `python-version` | No | `3.11` | Python version to use |

## Outputs

| Output | Description |
|---|---|
| `findings-count` | Total number of findings |
| `blocking-count` | Number of findings at or above fail-on threshold |
| `report-path` | Path to the output file (if output-file was set) |
| `gate-passed` | `true` or `false` |

## Complete Example

```yaml
name: VibeGuard
on: [pull_request]

permissions:
  contents: read
  security-events: write

jobs:
  vibeguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: dgenio/vibeguard@v0.7
        id: vibeguard
        with:
          diff: 'true'
          fail-on: 'high'
          output-format: 'sarif'
          output-file: 'vibeguard.sarif'

      - name: Upload SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: vibeguard.sarif
```
