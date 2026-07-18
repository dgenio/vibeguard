"""Hypothesis-driven fuzz tests for config loading (#55).

Goal: ``VibeGuardConfig.load`` must NEVER raise an unhandled exception on
malformed input. Acceptable failure modes are limited to:

* ``yaml.YAMLError`` — YAML parser detected a syntax error
* ``pydantic.ValidationError`` — schema validation rejected the document
* ``TypeError`` — YAML parsed to a non-mapping root (scalar, list, None)
* ``OSError`` — the filesystem could not be read
* ``RecursionError`` — deeply nested YAML exceeded Python's recursion limit

Anything else (``AttributeError``, ``KeyError``, ``IndexError``,
``UnicodeError``, …) indicates a defensive-coding gap inside the loader.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from vibeguard.config import VibeGuardConfig

# Hypothesis can be slow under coverage; bound runtime explicitly so CI
# stays predictable across Py 3.10/3.11/3.12.
# Override with HYPOTHESIS_MAX_EXAMPLES for deeper local exploration.
_DEFAULT_SETTINGS = settings(
    max_examples=int(os.environ.get("HYPOTHESIS_MAX_EXAMPLES", "50")),
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


@given(
    blob=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),  # exclude lone surrogates
        ),
        max_size=2000,
    )
)
@_DEFAULT_SETTINGS
def test_config_load_never_unhandled_on_arbitrary_text(blob: str, tmp_path: Path) -> None:
    """Random text as a config file must fail gracefully, not crash."""
    cfg_path = tmp_path / "vibeguard.yaml"
    cfg_path.write_text(blob, encoding="utf-8", errors="replace")
    # TypeError covers the case where YAML parses to a non-mapping root
    # (scalar, list, None) — pydantic raises a clean TypeError, which is
    # still a recognised failure mode, not a crash.
    with contextlib.suppress(yaml.YAMLError, ValidationError, OSError, TypeError):
        VibeGuardConfig.load(cfg_path)


@given(
    policy=st.sampled_from(["balanced", "strict", "relaxed", "aggressive", "", "BALANCED", "123"]),
    fail_on=st.sampled_from(
        ["info", "low", "medium", "high", "critical", "disaster", "", "CRITICAL"]
    ),
    max_kb=st.integers(min_value=-100, max_value=2_000_000),
)
@_DEFAULT_SETTINGS
def test_config_load_with_random_known_fields(
    policy: str, fail_on: str, max_kb: int, tmp_path: Path
) -> None:
    """Realistic-but-random values for known fields produce either a valid
    config or a clean ``ValidationError`` — never anything else."""
    cfg_path = tmp_path / "vibeguard.yaml"
    cfg_path.write_text(
        f"policy: {policy}\nfail_on: {fail_on}\nscanner:\n  max_file_size_kb: {max_kb}\n",
        encoding="utf-8",
    )
    try:
        cfg = VibeGuardConfig.load(cfg_path)
    except (ValidationError, yaml.YAMLError):
        return
    # If we got here, every value must be the canonical accepted form.
    assert cfg.policy in {"balanced", "strict", "relaxed"}
    assert cfg.scanner.max_file_size_kb >= 1


@given(deep_depth=st.integers(min_value=1, max_value=50))
@_DEFAULT_SETTINGS
def test_config_load_handles_deeply_nested_yaml(deep_depth: int, tmp_path: Path) -> None:
    """Deeply nested YAML must not blow up Python's default recursion limit."""
    payload = ":\n".join(["a" * 1] * deep_depth) + ": 1\n"
    cfg_path = tmp_path / "vibeguard.yaml"
    cfg_path.write_text(payload, encoding="utf-8")
    with contextlib.suppress(yaml.YAMLError, ValidationError, TypeError, RecursionError):
        VibeGuardConfig.load(cfg_path)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("", id="empty"),
        pytest.param("\x00", id="null-byte"),
        pytest.param("\n\n\n", id="whitespace-only"),
        pytest.param("key: \xff\xfe", id="encoding-edge"),
        pytest.param("policy: balanced\n\t\tfail_on: medium\n", id="tab-indentation"),
        pytest.param(":", id="malformed-mapping"),
        pytest.param("[1, 2, 3]", id="list-root"),
        # Explicit id is required: without it pytest derives an ~85 KB node id
        # from the payload, which overflows Windows' 32767-char limit on the
        # PYTEST_CURRENT_TEST environment variable and errors at setup (#167).
        pytest.param("policy: balanced\n" * 5000, id="very-long-duplicate"),
    ],
)
def test_config_load_known_pathological_inputs(payload: str, tmp_path: Path) -> None:
    """A curated set of pathological inputs must fail cleanly."""
    cfg_path = tmp_path / "vibeguard.yaml"
    cfg_path.write_bytes(payload.encode("utf-8", errors="replace"))
    with contextlib.suppress(yaml.YAMLError, ValidationError, TypeError, OSError):
        VibeGuardConfig.load(cfg_path)
