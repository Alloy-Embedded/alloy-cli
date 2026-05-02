"""Canonical performance budgets — single source of truth.

Mirrors the table in :file:`docs/ARCHITECTURE.md`.  A docs-sync
test asserts the two never drift.

Tolerance is multiplicative — ``ALLOY_PERF_TOLERANCE=2`` doubles
the budget for every benchmark.  CI runs at ``1.25`` to absorb
shared-runner noise.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# Budgets in seconds.  Keys MUST match the labels in
# docs/ARCHITECTURE.md exactly.
BUDGETS_SECONDS: Mapping[str, float] = {
    "alloy --help": 0.080,
    "alloy boards": 0.200,  # cached
    "alloy add uart": 0.500,
    "TUI startup": 0.300,  # to first paint
    "alloy build overhead": 0.050,
    "MCP tool call": 0.100,
}

CI_TOLERANCE = 1.25


def active_tolerance() -> float:
    """Read ``ALLOY_PERF_TOLERANCE`` from the environment.

    Returns the multiplicative factor applied to every budget.
    Defaults to :data:`CI_TOLERANCE` so CI runs feel a little
    slack (shared GitHub runners are noisy).
    """
    raw = os.environ.get("ALLOY_PERF_TOLERANCE")
    if raw is None:
        return CI_TOLERANCE
    try:
        value = float(raw)
    except ValueError:
        return CI_TOLERANCE
    return max(value, 1.0)


def effective_budget(label: str) -> float:
    """Return the budget for ``label`` scaled by the active tolerance."""
    if label not in BUDGETS_SECONDS:
        raise KeyError(f"Unknown perf budget label {label!r}")
    return BUDGETS_SECONDS[label] * active_tolerance()


__all__ = [
    "BUDGETS_SECONDS",
    "CI_TOLERANCE",
    "active_tolerance",
    "effective_budget",
]
