"""Board / device search benchmarks."""

from __future__ import annotations

import pytest

from tests.perf._budgets import effective_budget


@pytest.mark.perf
def test_search_boards_under_budget(benchmark) -> None:
    """Cached `alloy boards` search."""
    from alloy_cli.core import search as _search

    # Warm the cache so the benchmark measures the cached path.
    _search.search_boards()

    def _invoke() -> None:
        _search.search_boards()

    benchmark(_invoke)
    assert benchmark.stats["mean"] < effective_budget("alloy boards"), (
        f"search_boards mean {benchmark.stats['mean']:.3f}s "
        f"exceeded budget {effective_budget('alloy boards'):.3f}s"
    )


@pytest.mark.perf
def test_search_devices_admitted_under_budget(benchmark) -> None:
    """Admitted-only device search (no bulk YAML walk)."""
    from alloy_cli.core import search as _search

    _search.search_devices()

    def _invoke() -> None:
        _search.search_devices()

    benchmark(_invoke)
    # Admitted-only search rides the boards budget.
    assert benchmark.stats["mean"] < effective_budget("alloy boards")
