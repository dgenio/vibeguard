"""Base rule interface for VibeGuard.

This module defines the abstract :class:`Rule` interface that every built-in
and third-party VibeGuard rule must implement. The class is re-exported from
:mod:`vibeguard.api` under the alias ``BaseRule`` for plugin authors — see
``docs/plugin-api.md`` for the public-API contract and stability policy.

Implementations MUST:

* Be pure and deterministic *by default* — with the rule's default
  configuration, the same inputs must produce the same findings.
* Be offline by default — perform no network I/O on the default code path.
* Never raise exceptions out of :meth:`Rule.scan`; the scanner will treat any
  exception as a degraded run and surface it as a non-fatal error.
* Return only :class:`vibeguard.models.Finding` objects from :meth:`scan`.

Implementations MAY:

* Read files referenced by the :class:`vibeguard.models.ScanContext`.
* Override :meth:`is_applicable` to opt out of files outside the rule's
  domain (e.g. a Go-specific rule returning ``False`` for non-``.go`` files).
* Offer an **explicitly opt-in, off-by-default** networked check — but only
  when it is gated behind config, documented as such, isolated so it never
  raises, and the default (config-untouched) path stays offline and
  deterministic. The built-in ``slopsquat`` rule's ``registry_check`` is the
  reference example: it is ``false`` by default, so the offline guarantee
  above holds for every user who does not deliberately enable it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from vibeguard.models import Finding, ScanContext


class Rule(ABC):
    """Abstract base class for all VibeGuard rules.

    Concrete subclasses MUST set the ``id``, ``name`` and ``description``
    class attributes and implement :meth:`scan`. Subclasses SHOULD register
    a :class:`vibeguard.rules.registry.RuleMetadata` entry at import time
    via :func:`vibeguard.rules.registry.register_rule` so the rule appears
    in ``vibeguard rules list`` and the generated rule reference.
    """

    #: Stable rule identifier — used as the ``rule`` field on findings and
    #: as the key in the rule metadata registry. MUST be unique across all
    #: built-in and plugin rules.
    id: str

    #: Short human-readable name for tables / explain output.
    name: str

    #: One-sentence description of what the rule detects.
    description: str

    @abstractmethod
    def scan(self, context: ScanContext) -> list[Finding]:
        """Run the rule against the given scan context.

        Parameters
        ----------
        context:
            The shared :class:`vibeguard.models.ScanContext` for the current
            scan, containing the resolved root, the materialised file list,
            the parsed config, and (when available) git metadata.

        Returns
        -------
        list[Finding]
            All findings produced by this rule. Return an empty list when
            nothing is detected — do not return ``None``.

        Notes
        -----
        Implementations MUST NOT raise. The scanner wraps each rule in a
        try/except so a misbehaving plugin cannot bring down a scan, but
        the recommended discipline is to handle errors internally and emit
        an informational finding or simply skip the file.
        """
        ...

    def is_applicable(self, path: Path) -> bool:
        """Return ``True`` if this rule applies to ``path``.

        The default implementation returns ``True`` for every path — most
        rules iterate over the full file set in :meth:`scan` and filter
        internally. Override this when a rule is strictly scoped to a file
        family (e.g. Dockerfiles, Terraform) to skip unrelated files.

        Contract (#193):

        * The scanner calls this **once per candidate file per rule** and
          removes any path for which it returns ``False`` from the
          :class:`~vibeguard.models.ScanContext` that rule's :meth:`scan`
          receives (both ``files`` and ``changed_files``). A rule that returns
          ``False`` for a path is guaranteed never to see that path.
        * ``path`` is the same absolute :class:`~pathlib.Path` the scanner
          collected (resolved against the scan root); use ``path.name`` /
          ``path.suffix`` / ``path.parts`` rather than assuming a relative form.
        * Rules that inspect sibling files directly (e.g. file-level packaging
          or dependency rules) should leave the default in place rather than
          narrowing ``files``, since the scanner filters the whole context.
        * Overriding is a pure scoping optimisation — it must never change which
          findings a rule would otherwise produce. Keep it a conservative
          superset of the files the rule's :meth:`scan` actually acts on.
        """
        del path  # unused in default implementation
        return True

    def _rel(self, context: ScanContext, path: Path) -> str:
        """Return a ``/``-separated path relative to the scan root (#167)."""
        try:
            return path.relative_to(context.root).as_posix()
        except ValueError:
            return path.as_posix()


# Public alias for plugin authors. Importing from ``vibeguard.api`` is the
# stable entry point; the in-package ``Rule`` name is preserved so existing
# built-in rules continue to work unchanged.
BaseRule = Rule
"""Alias of :class:`Rule` for plugin authors. Re-exported from
:mod:`vibeguard.api`. Prefer the ``vibeguard.api`` import path in
third-party packages so dependency tracking is explicit."""
