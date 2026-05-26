# VibeGuard Plugin API

VibeGuard rules are pluggable. A third-party package can ship its own rules
and have them picked up automatically by every `vibeguard scan`, `gate`,
`publish-check`, and `rules list` invocation — without modifying the core.

This page is the stable reference for plugin authors. Anything documented
here will only break on a major bump of `PLUGIN_API_VERSION`.

## Stability contract

The public surface lives in **`vibeguard.api`**. Plugins must import
exclusively from there:

```python
from vibeguard.api import (
    BaseRule,        # the rule base class to subclass
    Confidence,      # finding confidence enum
    Finding,         # finding payload model
    GitMetadata,     # optional git context
    PLUGIN_API_VERSION,  # current API major.minor
    RULE_REGISTRY,   # read-only access to metadata
    RuleMetadata,    # the metadata to register
    register_rule,   # register your rule's metadata
    Rule,            # alias of BaseRule, for code that prefers the short name
    ScanContext,     # everything a rule needs to scan
    ScanResult,
    Severity,        # finding severity enum
)
```

Everything else under `vibeguard.*` is internal and may change without
notice. Don't import from `vibeguard.scanner`, `vibeguard.config`, or
deeper paths — open an issue if you need something that isn't exposed in
`vibeguard.api`.

`PLUGIN_API_VERSION` is a `"MAJOR.MINOR"` string. Plugins should pin a
range in their dependency metadata, e.g. `vibeguard-gate >=0.7,<1.0`,
until VibeGuard adopts a richer compatibility contract.

## Rule contract

A rule subclasses `BaseRule` and implements `scan(self, context) ->
list[Finding]`. The implementation:

| Must                                                          | Must not                                             |
|---------------------------------------------------------------|------------------------------------------------------|
| Be pure and deterministic                                     | Perform network I/O                                  |
| Return `list[Finding]` (empty list if nothing is found)       | Raise out of `scan()` — the scanner wraps every call, but you should handle errors internally |
| Be fast (< 100 ms per file is the soft target)                | Mutate global state in ways that bleed across rules  |
| Use a unique `id` and use it as the `rule` field on findings  | Reuse another rule's finding IDs                     |

`is_applicable(self, path) -> bool` defaults to `True`. Override it when
your rule only makes sense for a specific file family — the scanner can
short-circuit on it.

## Registering metadata

`RULE_REGISTRY` powers `vibeguard rules list`, `vibeguard rules explain`,
and the auto-generated rule reference (`docs/rules.md`). Register at
module import time:

```python
from vibeguard.api import RuleMetadata, register_rule

register_rule(
    RuleMetadata(
        rule_id="my-rule",
        title="My Custom Rule",
        description="One sentence on what the rule detects.",
        finding_ids=["MYRULE-TODO"],
        default_severity="low",     # info | low | medium | high | critical
        confidence="high",          # low | medium | high
        tags=["custom"],
        applies_to=["*.py"],
    )
)
```

`register_rule` raises `ValueError` if a `rule_id` is already taken.
Picking a unique, kebab-cased identifier prefixed with your distribution
name (e.g. `acme-foo`) is the safest convention.

## Distribution & discovery

Plugins are loaded through `importlib.metadata` entry points. Declare them
in your package's `pyproject.toml`:

```toml
[project.entry-points."vibeguard.rules"]
my-rule = "my_package.rules:MyRule"
```

The entry point can resolve to **either** a `BaseRule` subclass *or* a
zero-arg factory returning a `BaseRule` instance — the discovery layer
calls the resolved object once and validates the result.

On scanner startup the `vibeguard.rules` entry-point group is enumerated
and each plugin is instantiated in turn:

* Import errors, missing attributes, or wrong base class are caught and
  logged to stderr with a `[vibeguard] plugin warning:` prefix. A broken
  plugin **never** prevents the scan from running.
* Failed plugins also show up in `vibeguard rules list --list-plugins`
  with their failure reason.

To temporarily silence a plugin without uninstalling it, add it to your
`vibeguard.yaml`:

```yaml
plugins:
  disabled:
    - my-rule
```

The entry-point name (the left-hand side in the entry point declaration)
is the canonical disable key.

## Minimal worked example

A complete plugin distribution:

```
acme-vibeguard-rules/
├── pyproject.toml
└── acme_vg_rules/
    ├── __init__.py
    └── todo.py
```

`pyproject.toml`:

```toml
[project]
name = "acme-vibeguard-rules"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["vibeguard-gate>=0.6,<0.7"]

[project.entry-points."vibeguard.rules"]
acme-todo = "acme_vg_rules.todo:TodoRule"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`acme_vg_rules/todo.py`:

```python
from __future__ import annotations

from vibeguard.api import (
    BaseRule,
    Confidence,
    Finding,
    RuleMetadata,
    ScanContext,
    Severity,
    register_rule,
)


class TodoRule(BaseRule):
    id = "acme-todo"
    name = "ACME TODO scanner"
    description = "Flags TODO comments that mention an unresolved ticket."

    def scan(self, context: ScanContext) -> list[Finding]:
        findings: list[Finding] = []
        for path in context.files:
            if path.suffix != ".py":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "TODO" in line and "ACME-" in line:
                    findings.append(
                        Finding(
                            id="ACMETODO",
                            rule=self.id,
                            title="Unresolved ACME TODO",
                            description="Found a TODO referencing an ACME ticket.",
                            severity=Severity.LOW,
                            path=self._rel(context, path),
                            line=lineno,
                            recommendation="Resolve the ticket or remove the TODO.",
                            tags=["acme", "todo"],
                            confidence=Confidence.HIGH,
                        )
                    )
        return findings


register_rule(
    RuleMetadata(
        rule_id="acme-todo",
        title="ACME TODO scanner",
        description="Flags TODO comments that mention an unresolved ACME ticket.",
        finding_ids=["ACMETODO"],
        default_severity="low",
        confidence="high",
        tags=["acme", "todo"],
        applies_to=["*.py"],
    )
)
```

`pip install acme-vibeguard-rules` is enough — the next `vibeguard scan`
run picks up the rule and `vibeguard rules list --list-plugins` shows it
under `Discovered plugins`.

## Versioning policy

Backwards-incompatible changes to any symbol exported from
`vibeguard.api` bump the **major** component of `PLUGIN_API_VERSION`.
Backwards-compatible additions bump the minor.

* Major bumps (e.g. `1.0` → `2.0`): plugins pinned to `<2` will need
  updating. A future version of the discovery system will flag
  incompatible plugins and skip them at discovery time with a warning.
  Until that check is implemented, plugins must self-verify compatibility.
* Minor bumps (e.g. `1.0` → `1.1`): no plugin action required — new
  symbols become available; existing symbols keep their behaviour.

When VibeGuard ships a major bump, the release notes will document the
breaking changes and a migration recipe.
