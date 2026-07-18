"""Packaging-hygiene guards for the library-grade dependency policy (#121).

VibeGuard pip-installs into environments that already carry their own
dependency set (and often runs as a pre-commit hook / CI step), so its
dependency metadata must stay friendly to adopters:

* runtime deps use **lower bounds only** (``>=``) — no exact pins (``==``)
  and no speculative upper-bound caps;
* the advertised Python range (``requires-python`` + trove classifiers)
  covers 3.10 → 3.14 inclusive;
* ``constraints-min.txt`` stays in lockstep with the declared lower
  bounds, so the CI "floor deps" job actually exercises the versions we
  promise to support.

These are unit-level guards; the floor job in ``.github/workflows/ci.yml``
provides the runtime proof that the lower bounds resolve and pass.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
CONSTRAINTS_MIN = REPO_ROOT / "constraints-min.txt"

# Python versions VibeGuard advertises support for (inclusive).
EXPECTED_PYTHONS = ("3.10", "3.11", "3.12", "3.13", "3.14")

# Lean-core runtime-dependency budget (#248). VibeGuard's auditability pitch — a
# small, reviewable, offline tool inside the CI trust boundary — depends directly
# on a lean dependency surface, so the runtime deps are a fixed budget rather than
# something that accretes. Adding one requires updating this allowlist in the same
# PR (making the change visible in review) and justifying it against the criteria
# in CONTRIBUTING's "Dependency policy (lean core)". Heavier features belong behind
# an optional extra. Dev/test extras are a looser risk class and are not budgeted.
RUNTIME_DEPENDENCY_BUDGET = {
    "typer",
    "rich",
    "pydantic",
    "pyyaml",
    "pathspec",
    "tomli",  # TOML parser backport; installed only on Python < 3.11
}

# ``name (op version) [; marker]`` — enough to pull the package name, the
# comparator, and the version out of a PEP 508 requirement string.
_REQ_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)\s*(?P<op>[<>=!~]+)\s*(?P<version>[^;,\s]+)(?P<rest>.*)$"
)


def _load_pyproject() -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _runtime_requirements() -> list[str]:
    return _load_pyproject()["project"]["dependencies"]


def _parse_constraints() -> dict[str, str]:
    """Map ``name -> pinned version`` from constraints-min.txt."""
    pins: dict[str, str] = {}
    for raw in CONSTRAINTS_MIN.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _REQ_RE.match(line)
        assert m, f"Unparseable constraint line: {line!r}"
        assert m.group("op") == "==", (
            f"constraints-min.txt must pin exact floors with `==`, got {line!r}"
        )
        pins[m.group("name").lower()] = m.group("version")
    return pins


class TestDependencyPolicy:
    def test_runtime_deps_use_lower_bounds_only(self):
        """No exact pins and no upper-bound caps in runtime dependencies."""
        offenders: list[str] = []
        for req in _runtime_requirements():
            # Split off any environment marker before inspecting comparators.
            spec = req.split(";", 1)[0]
            if "==" in spec:
                offenders.append(f"{req} (exact pin)")
            if "<" in spec:
                offenders.append(f"{req} (upper-bound cap)")
            if ">=" not in spec:
                offenders.append(f"{req} (missing >= lower bound)")
        assert not offenders, (
            "Runtime dependencies must be lower-bound-only (see #121). "
            "Any retained cap needs an inline comment citing the specific "
            f"incompatibility. Offenders: {offenders}"
        )

    def test_constraints_min_matches_declared_lower_bounds(self):
        """Every runtime ``>=X`` must be pinned to ``==X`` in constraints-min.txt."""
        pins = _parse_constraints()
        declared: dict[str, str] = {}
        for req in _runtime_requirements():
            m = _REQ_RE.match(req)
            assert m, f"Unparseable dependency: {req!r}"
            declared[m.group("name").lower()] = m.group("version")

        missing = sorted(set(declared) - set(pins))
        extra = sorted(set(pins) - set(declared))
        assert not missing, (
            f"constraints-min.txt is missing floor pins for: {missing}. "
            "Add them so the floor CI job exercises the declared lower bounds."
        )
        assert not extra, f"constraints-min.txt pins packages not in runtime deps: {extra}."

        mismatched = {
            name: (declared[name], pins[name]) for name in declared if declared[name] != pins[name]
        }
        assert not mismatched, (
            "constraints-min.txt floors drifted from pyproject lower bounds "
            f"(declared vs pinned): {mismatched}"
        )


class TestDependencyBudget:
    """The runtime-dependency set is a fixed budget, guarded by an allowlist (#248).

    Separate from the lower-bounds-only *constraint style* above (#121): this
    guards the *count and kind* of runtime dependencies. A new runtime dep fails
    CI until it is consciously added to ``RUNTIME_DEPENDENCY_BUDGET`` in the same
    PR, forcing the tradeoff to be visible and justified.
    """

    def _declared_runtime_names(self) -> set[str]:
        names: set[str] = set()
        for req in _runtime_requirements():
            m = _REQ_RE.match(req)
            assert m, f"Unparseable dependency: {req!r}"
            names.add(m.group("name").lower())
        return names

    def test_runtime_dependencies_match_the_budget(self):
        declared = self._declared_runtime_names()
        budget = {name.lower() for name in RUNTIME_DEPENDENCY_BUDGET}

        added = sorted(declared - budget)
        removed = sorted(budget - declared)
        assert not added, (
            f"Runtime dependency added without updating the lean-core budget: {added}. "
            "If it is justified (see CONTRIBUTING → 'Dependency policy (lean core)'), add "
            "it to RUNTIME_DEPENDENCY_BUDGET in this file in the same PR; otherwise move "
            "the feature behind an optional extra in [project.optional-dependencies]."
        )
        assert not removed, (
            f"Runtime dependency removed but still listed in the budget: {removed}. "
            "Update RUNTIME_DEPENDENCY_BUDGET to match pyproject."
        )


class TestPythonSupportRange:
    def test_requires_python_has_no_upper_cap(self):
        requires = _load_pyproject()["project"]["requires-python"]
        assert requires == ">=3.10", (
            f"requires-python should be `>=3.10` with no upper cap, got {requires!r}"
        )

    def test_classifiers_list_every_supported_python(self):
        classifiers = _load_pyproject()["project"]["classifiers"]
        for version in EXPECTED_PYTHONS:
            needle = f"Programming Language :: Python :: {version}"
            assert needle in classifiers, f"Missing trove classifier: {needle!r}"
