"""``DebugScreen`` — Textual front-end for ``alloy debug --tui``.

Five panels driven by a :class:`core.gdb.GdbSession`:

- Source — current file with breakpoint gutter + PC arrow.
- Call stack — DataTable of stack frames.
- Locals + watches — Tree of variables.
- Registers — DataTable of register values.
- GDB log — RichLog mirroring every MI2 command + response.

Bindings: ``c`` continue, ``s`` step in, ``n`` step over,
``o`` finish, ``b`` toggle breakpoint at the cursor line,
``i`` interrupt, ``w`` add watch, ``Esc`` close.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, RichLog, Static, Tree

from alloy_cli.core.gdb import GdbSession, GdbSessionError, MiRecord


class DebugScreen(Screen[None]):
    """Five-panel debugger view driven by a :class:`GdbSession`."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Close"),
        Binding("c", "gdb_continue", "Continue"),
        Binding("s", "gdb_step", "Step in"),
        Binding("n", "gdb_next", "Step over"),
        Binding("o", "gdb_finish", "Step out"),
        Binding("b", "gdb_toggle_breakpoint", "Toggle bp"),
        Binding("i", "gdb_interrupt", "Interrupt"),
        Binding("w", "gdb_add_watch", "Add watch"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    DebugScreen #debug-grid {
        height: 1fr;
    }
    DebugScreen .debug-panel {
        border: round $primary;
        padding: 0 1;
    }
    DebugScreen #debug-source {
        height: 1fr;
        width: 60%;
    }
    DebugScreen #debug-stack {
        height: 1fr;
        width: 40%;
    }
    DebugScreen #debug-locals,
    DebugScreen #debug-registers,
    DebugScreen #debug-gdb-log {
        height: 1fr;
    }
    """

    def __init__(
        self,
        *,
        session: GdbSession,
        source_root: Path | None = None,
    ) -> None:
        super().__init__()
        self._session = session
        self._source_root = source_root or Path.cwd()
        # The Source panel binds these to the highlighted line as
        # the user navigates; for now they stay as raw strings (the
        # Source widget lands in a follow-up iteration).
        self._current_file: str | None = None
        self._current_line: int | None = None
        self._breakpoints: dict[tuple[str, int], str] = {}  # (file, line) -> bkpt_id

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Static(
                "[bold]Debug[/bold]  "
                "[dim]c continue · s step · n next · o finish · "
                "b breakpoint · i interrupt · w watch · Esc close[/dim]",
                id="debug-status",
            )
            with Horizontal(id="debug-grid"):
                yield RichLog(
                    id="debug-source",
                    classes="debug-panel",
                    markup=True,
                    highlight=False,
                )
                with Vertical():
                    yield DataTable(id="debug-stack", classes="debug-panel")
                    yield Tree("locals", id="debug-locals", classes="debug-panel")
                    yield DataTable(id="debug-registers", classes="debug-panel")
            yield RichLog(
                id="debug-gdb-log",
                classes="debug-panel",
                markup=False,
                highlight=False,
                max_lines=2_000,
            )
        yield Footer()

    def on_mount(self) -> None:
        stack = self.query_one("#debug-stack", DataTable)
        stack.add_columns("level", "func", "file:line")
        regs = self.query_one("#debug-registers", DataTable)
        regs.add_columns("name", "value")
        # Mirror the session's existing log into the panel so the user
        # sees how we got here.
        log = self.query_one("#debug-gdb-log", RichLog)
        for record in self._session.log:
            log.write(record.text)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        self._session.close()
        self.dismiss(None)

    def action_gdb_continue(self) -> None:
        self._issue("-exec-continue")

    def action_gdb_step(self) -> None:
        self._issue("-exec-step")

    def action_gdb_next(self) -> None:
        self._issue("-exec-next")

    def action_gdb_finish(self) -> None:
        self._issue("-exec-finish")

    def action_gdb_interrupt(self) -> None:
        self._issue("-exec-interrupt --all")

    def action_gdb_toggle_breakpoint(self) -> None:
        if self._current_file is None or self._current_line is None:
            self.notify(
                "Place the cursor on a Source line first.", severity="warning"
            )
            return
        key = (str(self._current_file), int(self._current_line))
        existing = self._breakpoints.get(key)
        if existing is not None:
            try:
                self._session.delete_breakpoint(existing)
            except GdbSessionError as exc:
                self.notify(f"Couldn't delete breakpoint: {exc}", severity="error")
                return
            del self._breakpoints[key]
            self.notify(f"Removed breakpoint at {key[0]}:{key[1]}.", severity="information")
            return
        try:
            record = self._session.set_breakpoint(f"{key[0]}:{key[1]}")
        except GdbSessionError as exc:
            self.notify(f"Couldn't set breakpoint: {exc}", severity="error")
            return
        # MI2 returns the number nested under ``bkpt={number="3",...}``.
        # The flat parser preserves the nested string so we regex it.
        import re

        bkpt_id = ""
        if "bkpt" in record.payload:
            m = re.search(r'number="(\d+)"', record.payload["bkpt"])
            if m:
                bkpt_id = m.group(1)
        if not bkpt_id:
            bkpt_id = record.payload.get("number", "")
        if bkpt_id:
            self._breakpoints[key] = bkpt_id
        self.notify(f"Breakpoint at {key[0]}:{key[1]}.", severity="information")
        self._echo_log(record)

    def action_gdb_add_watch(self) -> None:
        # The watch flow is a small modal — for now we surface a
        # notify so the binding is discoverable; the modal lands in
        # a follow-up TUI iteration.
        self.notify(
            "Watch expressions land in a follow-up TUI iteration; for "
            "now use `-data-evaluate-expression` via the GDB log.",
            severity="information",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _issue(self, command: str) -> None:
        try:
            record = self._session.issue(command)
        except GdbSessionError as exc:
            self.notify(f"GDB error: {exc}", severity="error")
            return
        self._echo_log(record)

    def _echo_log(self, record: MiRecord) -> None:
        log = self.query_one("#debug-gdb-log", RichLog)
        log.write(record.text)


__all__ = ["DebugScreen"]
