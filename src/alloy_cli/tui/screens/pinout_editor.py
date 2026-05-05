"""``PinoutEditorScreen`` — in-project schematic with peripheral-add flow.

Differences from the read-only :class:`PinoutScreen` (used by
``alloy boards <id> --pinout``):

* **Project context**: loads ``alloy.toml`` + device IR from the
  current project; shows existing pin assignments in ASSIGNED state.
* **Editing**: a row of buttons launches :class:`PeripheralAddScreen`
  for the chosen peripheral kind (UART / SPI / I2C / GPIO / …).
* **Live refresh**: after each :class:`PeripheralAddScreen` dismisses,
  the config is re-read and the schematic is updated in place.
* **Registry entry**: accessible from the TUI command palette as
  ``pinout-editor``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets.pinout import PinoutMode, PinoutWidget, rows_from_ir

# Ordered list of addable peripheral kinds; labels shown on the buttons.
_KINDS: tuple[tuple[str, str], ...] = (
    ("uart",  "UART"),
    ("spi",   "SPI"),
    ("i2c",   "I2C"),
    ("gpio",  "GPIO"),
    ("timer", "Timer"),
    ("adc",   "ADC"),
    ("can",   "CAN"),
    ("usb",   "USB"),
    ("eth",   "ETH"),
)


class PinoutEditorScreen(Screen[None]):
    """Interactive schematic view bound to the current project.

    Shows every pin of the target device with its current assignment
    state.  A row of buttons at the bottom launches the peripheral-add
    flow; the schematic refreshes automatically after each successful
    add so the user always sees the live state.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Close"),
        Binding("f3", "toggle_mode", "Compact"),
        Binding("f5", "reload", "Reload"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    PinoutEditorScreen #editor-root {
        padding: 0 1;
    }
    PinoutEditorScreen #editor-header-line {
        height: 1;
        margin-bottom: 1;
    }
    PinoutEditorScreen #add-label {
        height: 1;
        margin-top: 1;
    }
    PinoutEditorScreen #add-buttons {
        height: 3;
        margin-top: 0;
    }
    PinoutEditorScreen #add-buttons Button {
        margin: 0 1 0 0;
        min-width: 7;
    }
    """

    def __init__(
        self,
        *,
        project_dir: Path,
        config: object,        # ProjectConfig — typed loosely to avoid circular import at class-body time
        device: object,        # DeviceIR
        terminal_width: int = 140,
    ) -> None:
        super().__init__()
        self._project_dir = project_dir
        self._config = config
        self._device = device
        self._terminal_width = terminal_width

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        from alloy_cli.core.ir import DeviceIR

        yield Header(show_clock=False)
        with Vertical(id="editor-root"):
            dev: DeviceIR = self._device  # type: ignore[assignment]
            pkg_label = (
                f"{dev.package.name.upper()} · {dev.package.pin_count} pads"
                if dev.package is not None
                else "no package data"
            )
            yield Static(
                f"[bold]{dev.identity.device}[/bold]  "
                f"[dim]{pkg_label}  ·  F3 compact  ·  F5 reload  ·  ESC close[/dim]",
                id="editor-header-line",
            )
            yield PinoutWidget(
                self._build_rows(),
                package=dev.package,
                mode=PinoutMode.SCHEMATIC,
                terminal_width=self._terminal_width,
                id="editor-pinout",
            )
            yield Static("[bold]Add peripheral[/bold]", id="add-label")
            with Horizontal(id="add-buttons"):
                for kind, label in _KINDS:
                    yield Button(label, id=f"add-{kind}", variant="default")
        yield Footer()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Launch PeripheralAddScreen for the chosen kind."""
        btn_id = event.button.id or ""
        if not btn_id.startswith("add-"):
            return
        kind = btn_id.removeprefix("add-")
        from alloy_cli.tui.screens.peripheral_add import PeripheralAddScreen

        self.app.push_screen(
            PeripheralAddScreen(
                kind=kind,
                project_dir=self._project_dir,
                config=self._config,   # type: ignore[arg-type]
                device=self._device,   # type: ignore[arg-type]
            ),
            callback=self._after_add,
        )

    def _after_add(self, _result: object) -> None:
        """Reload config + refresh schematic after PeripheralAddScreen closes."""
        self.action_reload()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_toggle_mode(self) -> None:
        self.query_one("#editor-pinout", PinoutWidget).toggle_mode()

    def action_reload(self) -> None:
        """Re-read alloy.toml and repaint the schematic."""
        from alloy_cli.core.errors import AlloyCliError
        from alloy_cli.core.project import PROJECT_FILE, read as _read

        try:
            self._config = _read(self._project_dir / PROJECT_FILE)
        except AlloyCliError:
            pass
        self._refresh_pinout()
        self.notify("Pinout refreshed.", severity="information", timeout=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_rows(self) -> tuple:
        from alloy_cli.core import conflicts as _conflicts

        assignments: dict[str, str] = {}
        if self._config is not None:
            peripherals = getattr(self._config, "peripherals", [])
            for pin, claim in _conflicts.existing_pin_claims(peripherals).items():
                assignments[pin] = claim.holder
        return rows_from_ir(self._device, assignments=assignments)  # type: ignore[arg-type]

    def _refresh_pinout(self) -> None:
        widget = self.query_one("#editor-pinout", PinoutWidget)
        widget.set_rows(self._build_rows())


# ---------------------------------------------------------------------------
# Placeholder shown when no project / device IR is available
# ---------------------------------------------------------------------------


class _PinoutEditorPlaceholder(Screen[None]):
    DEFAULT_CSS: ClassVar[str] = """
    _PinoutEditorPlaceholder {
        align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "Pinout editor requires a project with a resolved [chip] or [board].\n"
            "Open a project directory that contains [bold]alloy.toml[/bold] and try again."
        )


# ---------------------------------------------------------------------------
# Registry factory
# ---------------------------------------------------------------------------


def _load_pinout_editor_context(
    project_dir: Path,
) -> tuple[object, object] | None:
    """Return (config, device) or None."""
    from alloy_cli.core.errors import AlloyCliError
    from alloy_cli.core.project import PROJECT_FILE, read as _read

    toml = project_dir / PROJECT_FILE
    if not toml.exists():
        return None
    try:
        config = _read(toml)
    except AlloyCliError:
        return None

    from alloy_cli.tui.screens.peripheral_add import _resolve_device_for

    device = _resolve_device_for(config)  # type: ignore[arg-type]
    if device is None:
        return None
    return config, device


@register_screen(
    "pinout-editor",
    title="Pinout editor",
    description="In-project schematic with peripheral-add flow",
)
def make_pinout_editor() -> Screen:
    """Build a live PinoutEditorScreen from the project in CWD.

    Walks up from the current working directory to find ``alloy.toml``,
    resolves the device IR, and returns a fully-wired editor.  Returns
    a placeholder when no project or device IR is found.
    """
    cwd = Path(os.getcwd()).resolve()
    for parent in [cwd, *cwd.parents]:
        ctx = _load_pinout_editor_context(parent)
        if ctx is not None:
            config, device = ctx
            return PinoutEditorScreen(
                project_dir=parent,
                config=config,
                device=device,
            )
    return _PinoutEditorPlaceholder()


__all__ = ["PinoutEditorScreen", "make_pinout_editor"]
