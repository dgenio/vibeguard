"""Packaging-hygiene guards for the library-grade dependency policy (#121).

VibeGuard pip-installs into environments that already carry their own
dependency set (and often runs as a pre-commit hook / CI step), so its
dependency metadata must stay friendly to adopters:

* runtime deps use **lower bounds only** (``>=``) — no exact pins (``==``)
  and no speculative upper-bound caps;
* the advertised Python range (``requires-python`` + trove classifiers)
  covers 3.10 → 3.14 inclusive;
* ``pyproject.toml`` is the single source of truth for dependency floors. The
  CI floor job resolves those declarations directly with uv ``lowest-direct``.

These are unit-level guards; the floor job in ``.github/workflows/ci.yml``
provides the runtime proof that the lower bounds resolve and pass.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

EXPECTED_PYTHONS = ("3.10", "3.11", "3.12", "3.13", "3.14")

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


class TestDependencyPolicy:
    def test_runtime_deps_use_lower_bounds_only(self):
        """Every runtime dependency exposes one parseable >= floor and no cap."""
        offenders: list[str] = []
        for req in _runtime_requirements():
            spec = req.split(";", 1)[0]
            match = _REQ_RE.match(req)
            if match is None:
                offenders.append(f"{req} (unparseable requirement)")
                continue
            if "==" in spec:
                offenders.append(f"{req} (exact pin)")
            if "<" in spec:
                offenders.append(f"{req} (upper-bound cap)")
            if match.group("op") != ">=":
                offenders.append(f"{req} (must declare a >= floor)")
        assert not offenders, (
            "Runtime dependencies must be lower-bound-only (see #121). "
            "Any retained cap needs an inline comment citing the specific "
            f"incompatibility. Offenders: {offenders}"
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
