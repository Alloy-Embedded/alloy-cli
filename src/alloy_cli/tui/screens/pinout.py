"""``PinoutScreen`` — read-only schematic view for ``alloy boards <id> --pinout``.

The screen is intentionally minimal — no editing, no peripheral
flow.  It mounts the existing :class:`PinoutWidget` in schematic
mode plus a footer showing legend + ESC/F3 hints.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli.core.ir import DeviceIR
from alloy_cli.tui.widgets.pinout import PinoutMode, PinoutWidget, rows_from_ir


class PinoutScreen(Screen[None]):
    """Read-only schematic view of a device's package."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Close"),
        Binding("f3", "toggle_mode", "Toggle compact"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    PinoutScreen #pinout-root {
        padding: 0 1;
    }
    """

    def __init__(
        self,
        ir: DeviceIR,
        *,
        terminal_width: int = 140,
    ) -> None:
        super().__init__()
        self._ir = ir
        self._terminal_width = terminal_width

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="pinout-root"):
            yield Static(
                f"[bold]{self._ir.identity.device}[/bold]  "
                f"[dim]ESC close · F3 compact[/dim]"
            )
            if self._ir.package is None:
                yield Static(
                    "[yellow]No package layout available for this device.[/yellow]"
                )
            yield PinoutWidget(
                rows_from_ir(self._ir),
                package=self._ir.package,
                mode=PinoutMode.SCHEMATIC,
                terminal_width=self._terminal_width,
                id="pinout-widget",
            )
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_toggle_mode(self) -> None:
        widget = self.query_one("#pinout-widget", PinoutWidget)
        widget.toggle_mode()


__all__ = ["PinoutScreen"]
