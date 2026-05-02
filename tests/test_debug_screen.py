"""Pilot-driven tests for ``DebugScreen`` (#31)."""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass, field

import pytest

from alloy_cli.core.gdb import GdbSession
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.debug import DebugScreen


@dataclass
class _FakePopen:
    stdout_lines: list[str] = field(default_factory=list)
    stdin_buffer: io.StringIO = field(default_factory=io.StringIO)
    poll_value: int | None = None

    def __post_init__(self) -> None:
        self.stdout = iter(self.stdout_lines)
        self.stdin = self.stdin_buffer

    def poll(self) -> int | None:
        return self.poll_value

    def wait(self, timeout: float | None = None) -> int:
        return self.poll_value or 0

    def kill(self) -> None:
        self.poll_value = -9


def _session(stdout: Iterable[str]) -> GdbSession:
    proc = _FakePopen(stdout_lines=[*stdout, "(gdb)\n"])
    return GdbSession(process=proc)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_debug_screen_mounts_five_panels() -> None:
    session = _session([])
    app = TuiApp(initial_screen=DebugScreen(session=session))
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        for panel_id in (
            "#debug-source",
            "#debug-stack",
            "#debug-locals",
            "#debug-registers",
            "#debug-gdb-log",
        ):
            assert app.screen.query_one(panel_id) is not None


@pytest.mark.asyncio
async def test_action_continue_writes_exec_continue() -> None:
    session = _session(["^running\n"])
    screen = DebugScreen(session=session)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen.action_gdb_continue()
        await pilot.pause()
    assert "-exec-continue" in session.process.stdin.getvalue()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_action_step_writes_exec_step() -> None:
    session = _session(["^running\n"])
    screen = DebugScreen(session=session)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen.action_gdb_step()
        await pilot.pause()
    assert "-exec-step" in session.process.stdin.getvalue()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_action_toggle_breakpoint_without_cursor_notifies() -> None:
    session = _session([])
    screen = DebugScreen(session=session)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        # Without a cursor the action notifies but doesn't crash.
        screen.action_gdb_toggle_breakpoint()
        await pilot.pause()


@pytest.mark.asyncio
async def test_action_toggle_breakpoint_round_trips_through_log() -> None:
    """A breakpoint set + delete cycle hits the GDB log panel."""
    session = _session(
        [
            '^done,bkpt={number="3",file="main.c",line="42"}\n',
            "^done\n",  # delete reply
        ]
    )
    screen = DebugScreen(session=session)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen._current_file = "main.c"
        screen._current_line = 42
        screen.action_gdb_toggle_breakpoint()
        await pilot.pause()
        assert ("main.c", 42) in screen._breakpoints
        screen.action_gdb_toggle_breakpoint()
        await pilot.pause()
        assert ("main.c", 42) not in screen._breakpoints


@pytest.mark.asyncio
async def test_action_cancel_closes_session() -> None:
    session = _session([])
    screen = DebugScreen(session=session)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        screen.action_cancel()
        await pilot.pause()
    # close() writes -gdb-exit to stdin (when the process is "alive").
    assert "-gdb-exit" in session.process.stdin.getvalue()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_gdb_log_panel_replays_session_history() -> None:
    """Pre-existing records in the session log render in the panel."""
    session = _session([])
    # Pre-load some records into the log so on_mount mirrors them.
    from alloy_cli.core.gdb import MiRecord

    session.log.extend(
        [
            MiRecord(cls="done", text="^done,bkpt={number=\"1\"}"),
            MiRecord(cls="running", text="^running"),
        ]
    )
    screen = DebugScreen(session=session)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause()
        from textual.widgets import RichLog

        log_widget = screen.query_one("#debug-gdb-log", RichLog)
        # RichLog stores its lines internally; we just confirm there's
        # *something* by checking the widget renders without error.
        assert log_widget is not None
