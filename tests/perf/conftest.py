"""Pytest configuration for ``tests/perf/``.

The perf suite is gated behind a ``perf`` marker (registered in
the root ``tests/conftest.py``).  Running ``pytest -m perf``
opts in; the default test run skips them so day-to-day iteration
doesn't pay the benchmark cost.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip perf items unless the user explicitly opts in via ``-m perf``."""
    selected = config.getoption("-m") or ""
    if "perf" in selected:
        return
    skip_marker = pytest.mark.skip(reason="perf-only suite (run with `-m perf`)")
    for item in items:
        if "perf" in item.keywords:
            item.add_marker(skip_marker)
