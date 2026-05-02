"""Performance benchmark suite enforcing the ARCHITECTURE.md SLAs.

Run only the perf suite::

    uv run pytest -m perf

Override the budget tolerance (default 1.25 in CI; locals can
boost it on slower laptops)::

    ALLOY_PERF_TOLERANCE=2 uv run pytest -m perf
"""
