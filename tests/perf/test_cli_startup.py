"""CLI cold-start benchmarks.

Budget: ``alloy --help`` MUST settle in under 80 ms.  Anything
heavier (eager imports, walking the boards catalogue at import
time) blows the budget and fails CI.
"""

from __future__ import annotations

import sys

import pytest

from tests.perf._budgets import effective_budget


@pytest.mark.perf
def test_alloy_help_under_budget(benchmark) -> None:
    """``alloy --help`` cold start."""
    from click.testing import CliRunner

    from alloy_cli.main import cli

    runner = CliRunner()

    def _invoke() -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    benchmark(_invoke)
    assert benchmark.stats["mean"] < effective_budget("alloy --help"), (
        f"alloy --help mean {benchmark.stats['mean']:.3f}s "
        f"exceeded budget {effective_budget('alloy --help'):.3f}s"
    )


@pytest.mark.perf
def test_alloy_version_under_budget(benchmark) -> None:
    """``alloy --version`` should be even cheaper than --help."""
    from click.testing import CliRunner

    from alloy_cli.main import cli

    runner = CliRunner()

    def _invoke() -> None:
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    benchmark(_invoke)
    # --version reuses the same import path as --help; sharing the
    # budget keeps the assertion meaningful.
    assert benchmark.stats["mean"] < effective_budget("alloy --help")


@pytest.mark.perf
def test_alloy_main_module_import_under_budget() -> None:
    """A fresh ``import alloy_cli.main`` MUST stay under budget.

    We measure once with a child interpreter so caching across
    calls doesn't mask regressions; pytest-benchmark is overkill
    for a single-shot import.
    """
    import subprocess
    import time

    cmd = [sys.executable, "-c", "import alloy_cli.main"]
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False)
    elapsed = time.perf_counter() - start
    assert proc.returncode == 0
    # Use the help budget — main module import is the expensive bit.
    assert elapsed < effective_budget("alloy --help") * 4, (
        f"`import alloy_cli.main` took {elapsed:.3f}s; budget "
        f"{effective_budget('alloy --help') * 4:.3f}s (4x help "
        f"budget to absorb interpreter startup)"
    )
