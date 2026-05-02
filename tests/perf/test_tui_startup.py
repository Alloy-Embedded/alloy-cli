"""TUI first-paint benchmarks."""

from __future__ import annotations

import asyncio

import pytest

from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.welcome import WelcomeScreen
from tests.perf._budgets import effective_budget


@pytest.mark.perf
def test_welcome_first_paint_under_budget(benchmark) -> None:
    """The Welcome screen MUST hit first paint inside the TUI budget."""

    async def _render() -> None:
        app = TuiApp(initial_screen=WelcomeScreen())
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()

    def _invoke() -> None:
        asyncio.run(_render())

    benchmark(_invoke)
    # 4x the budget to absorb asyncio + pilot setup overhead;
    # tightening to 1x is a follow-up once we strip Pilot from the
    # measurement (e.g. by hooking `app._on_idle`).
    assert benchmark.stats["mean"] < effective_budget("TUI startup") * 4, (
        f"welcome first paint mean {benchmark.stats['mean']:.3f}s "
        f"exceeded 4x budget "
        f"{effective_budget('tui startup') * 4:.3f}s"
    )
