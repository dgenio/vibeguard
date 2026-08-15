"""Inline suppression parser for VibeGuard."""

from __future__ import annotations

import re

# Matches: # vibeguard: ignore ID1,ID2 reason="some reason"
# Recognised single-line comment leaders cover the syntaxes VibeGuard scans
# (#210). The HTML/Markdown leader is listed first so a ``<!-- ... -->`` wrapper
# is matched as a whole rather than via the ``--`` inside it:
#   <!--  HTML, Markdown  (e.g. <!-- vibeguard: ignore ID reason="..." -->)
#   //    JS/TS, Go, HCL
#   --    SQL
#   #     Python, shell, YAML, TOML, Dockerfile, HCL
# The suppression *directive* must sit on a single physical line; multi-line
# block comments (``/* ... */``) are not recognised. Placement is same-line or
# the line directly above the finding (see scanner._apply_inline_suppressions).
# Leaders are not scoped by file type — any recognised leader is accepted in any
# suppression-eligible file (so ``--`` works in Markdown, ``<!--`` in SQL, and a
# ``--`` inside a SQL string literal can read as a suppression). #210 accepts
# this: the ``vibeguard: ignore`` marker is specific enough that an accidental
# match is implausible, and a per-suffix leader map is not worth the complexity.
_SUPPRESSION_RE = re.compile(
    r"(?:<!--|//|--|#)\s*vibeguard:\s*ignore\s+"
    r"(?P<ids>[A-Z][A-Z0-9\-,]+)"
    r'(?:\s+reason\s*=\s*"(?P<reason>[^"]*)")?'
)


def parse_inline_suppressions(content: str) -> dict[int, list[str]]:
    """Parse valid inline suppression comments from file content.

    Returns a mapping of line_number -> list of suppressed finding IDs. Line
    numbers are 1-based. A suppression without a non-blank ``reason=`` is not
    authoritative and is therefore excluded from this map; callers can surface
    it separately through :func:`find_missing_reasons` without hiding the
    underlying finding (#132).
    """
    suppressions: dict[int, list[str]] = {}
    for lineno, line in enumerate(content.splitlines(), start=1):
        match = _SUPPRESSION_RE.search(line)
        if match:
            reason = match.group("reason")
            if reason is None or not reason.strip():
                continue
            ids = [fid.strip() for fid in match.group("ids").split(",") if fid.strip()]
            suppressions[lineno] = ids
    return suppressions


def find_missing_reasons(content: str) -> list[tuple[int, list[str]]]:
    """Find inline suppressions that are missing a reason= argument.

    Returns list of (line_number, finding_ids) for suppressions without reasons.
    """
    missing: list[tuple[int, list[str]]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        match = _SUPPRESSION_RE.search(line)
        if match:
            reason = match.group("reason")
            if reason is None or reason.strip() == "":
                ids = [fid.strip() for fid in match.group("ids").split(",") if fid.strip()]
                missing.append((lineno, ids))
    return missing
