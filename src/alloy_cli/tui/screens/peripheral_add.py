"""``PeripheralAddScreen`` — IR-validated peripheral wiring TUI."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from alloy_cli.core import conflicts as _conflicts
from alloy_cli.core import peripherals as _peripherals
from alloy_cli.core.diagnostics import Diagnostic
from alloy_cli.core.errors import (
    AlloyCliError,
    BoardNotFoundError,
    DataRepoMissingError,
    DeviceNotFoundError,
    ProjectConfigError,
)
from alloy_cli.core.ir import DeviceIR, valid_pins_for
from alloy_cli.core.peripherals import AddArgs, AddResult
from alloy_cli.core.project import PROJECT_FILE, ProjectConfig, read
from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets import (
    DiffModal,
    PinoutWidget,
    ValidationPanel,
    rows_from_ir,
)

_DEFAULT_KIND = "uart"


class PeripheralAddScreen(Screen[None]):
    """Screen 3 from ``docs/TUI_DESIGN.md`` — peripheral wiring + live validation."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+d", "show_diff", "Diff", show=True),
        Binding("ctrl+s", "apply", "Apply", show=True),
        Binding("f3", "toggle_pinout_mode", "Pinout mode", show=True),
        Binding("escape", "cancel", "Close", show=False),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    PeripheralAddScreen #peripheral-root {
        padding: 0 1;
    }
    PeripheralAddScreen .panel {
        padding: 0 1;
        border-top: solid $primary;
    }
    PeripheralAddScreen #peripheral-actions {
        height: 3;
        align: right middle;
    }
    """

    def __init__(
        self,
        *,
        kind: str,
        project_dir: Path,
        config: ProjectConfig | None = None,
        device: DeviceIR | None = None,
    ) -> None:
        super().__init__()
        self._kind = kind.lower()
        self._project_dir = project_dir.resolve()
        self._config = config
        self._device = device
        self._error: str | None = None
        self._result: AddResult | None = None
        self._initial_load_error: str | None = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        if self._config is None:
            try:
                self._config = read(self._project_dir / PROJECT_FILE)
            except (ProjectConfigError, OSError) as exc:
                self._initial_load_error = f"Cannot read alloy.toml: {exc}"
        if self._device is None and self._config is not None:
            self._device = _resolve_device_for(self._config)
            if self._device is None:
                self._initial_load_error = (
                    "alloy.toml has no [chip] / [board] target — cannot resolve device IR."
                )
        self._refresh()

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="peripheral-root"):
            yield Static(f"[bold]Add {self._kind}[/bold] peripheral", classes="panel")
            yield Input(placeholder="name (e.g. console)", id="field-name")
            yield Input(placeholder="peripheral instance (optional)", id="field-peripheral")
            yield from self._compose_kind_fields()
            yield PinoutWidget(id="peripheral-pinout")
            yield ValidationPanel(id="peripheral-validation")
            yield Static("", id="peripheral-status", classes="panel")
            with Horizontal(id="peripheral-actions"):
                yield Button(
                    "Diff",
                    id="diff-button",
                    tooltip="Show the alloy.toml + peripherals.cpp diff before applying.",
                )
                yield Button(
                    "Apply",
                    id="apply-button",
                    variant="success",
                    tooltip="Write the diff to disk (Ctrl+S also applies).",
                )
        yield Footer()

    def _compose_kind_fields(self) -> ComposeResult:
        if self._kind == "uart":
            yield Input(placeholder="tx pin (optional)", id="field-tx")
            yield Input(placeholder="rx pin (optional)", id="field-rx")
            yield Input(placeholder="baud (default 115200)", id="field-baud")
        elif self._kind == "gpio":
            yield Input(placeholder="pin (required)", id="field-pin")
            yield Input(placeholder="mode (input/output/od/analog/alternate)", id="field-mode")
        elif self._kind == "spi":
            yield Input(placeholder="sck pin (optional)", id="field-sck")
            yield Input(placeholder="miso pin (optional)", id="field-miso")
            yield Input(placeholder="mosi pin (optional)", id="field-mosi")
        elif self._kind == "i2c":
            yield Input(placeholder="sda pin (optional)", id="field-sda")
            yield Input(placeholder="scl pin (optional)", id="field-scl")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "diff-button":
            self.action_show_diff()
        elif event.button.id == "apply-button":
            self.action_apply()

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def _collect_overrides(self) -> tuple[str, dict[str, str]]:
        name = ""
        if self.query("#field-name"):
            name = self.query_one("#field-name", Input).value.strip()
        overrides: dict[str, str] = {}
        for field in (
            "peripheral",
            "tx",
            "rx",
            "baud",
            "pin",
            "mode",
            "sck",
            "miso",
            "mosi",
            "sda",
            "scl",
        ):
            inputs = self.query(f"#field-{field}")
            if inputs:
                first = next(iter(inputs))
                value = first.value.strip()  # type: ignore[union-attr]
                if value:
                    overrides[field] = value
        return name, overrides

    def _refresh(self) -> None:
        if self._initial_load_error is not None:
            self._set_status(self._initial_load_error, is_error=True)
            return
        if self._config is None or self._device is None:
            return

        name, overrides = self._collect_overrides()
        if not name:
            self._set_status("Choose a name to begin.", is_error=False)
            self._update_validation(())
            self._refresh_pinout(set(), overrides.get("peripheral"))
            self._toggle_apply(disabled=True)
            return

        args = AddArgs.of(name, **overrides)
        try:
            self._result = self._dispatch(self._config, self._device, args)
        except (AlloyCliError, KeyError, TypeError) as exc:
            self._set_status(f"add_{self._kind}: {exc}", is_error=True)
            self._toggle_apply(disabled=True)
            return

        self._update_validation(self._result.diagnostics)
        self._refresh_pinout(self._candidate_pins(), overrides.get("peripheral"))
        if self._result.has_errors:
            self._set_status(
                f"{sum(1 for d in self._result.diagnostics if d.severity == 'error')} error(s).",
                is_error=True,
            )
            self._toggle_apply(disabled=True)
        else:
            patches = self._result.diff.patches if self._result.diff else ()
            files = ", ".join(str(p.path) for p in patches if p.changed) or "(no diff)"
            self._set_status(f"Will modify: {files}", is_error=False)
            self._toggle_apply(disabled=not self._result.diff.changed)

    def _dispatch(self, config: ProjectConfig, ir: DeviceIR, args: AddArgs) -> AddResult:
        if self._kind == "uart":
            return _peripherals.add_uart(config, ir, args)
        if self._kind == "gpio":
            return _peripherals.add_gpio(config, ir, args)
        if self._kind == "spi":
            return _peripherals.add_spi(config, ir, args)
        if self._kind == "i2c":
            return _peripherals.add_i2c(config, ir, args)
        return _peripherals.add_generic(config, ir, self._kind, args)

    def _candidate_pins(self) -> set[str]:
        if self._device is None or self._result is None or self._result.proposed is None:
            return set()
        proposed = self._result.proposed
        instance = proposed.payload.get("peripheral")
        if not isinstance(instance, str):
            return set()
        signals = {
            "uart": ("TX", "RX"),
            "spi": ("SCK", "MISO", "MOSI"),
            "i2c": ("SDA", "SCL"),
        }.get(self._kind, ())
        candidates: set[str] = set()
        for signal in signals:
            for pin in valid_pins_for(self._device, peripheral=instance, signal=signal):
                candidates.add(pin)
        return candidates

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------

    def _refresh_pinout(self, candidates: set[str], _instance: str | None) -> None:
        if self._device is None:
            return
        assignments: dict[str, str] = {}
        if self._config is not None:
            for pin, claim in _conflicts.existing_pin_claims(self._config.peripherals).items():
                assignments[pin] = claim.holder
        rows = rows_from_ir(self._device, candidates=candidates, assignments=assignments)
        widget = self.query_one("#peripheral-pinout", PinoutWidget)
        widget.set_rows(rows)

    def _update_validation(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        panel = self.query_one("#peripheral-validation", ValidationPanel)
        panel.update_diagnostics(diagnostics)

    def _set_status(self, text: str, *, is_error: bool) -> None:
        widget = self.query_one("#peripheral-status", Static)
        prefix = "[red]" if is_error else "[green]"
        suffix = "[/red]" if is_error else "[/green]"
        widget.update(f"{prefix}{text}{suffix}")

    def _toggle_apply(self, *, disabled: bool) -> None:
        button = self.query_one("#apply-button", Button)
        button.disabled = disabled

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_show_diff(self) -> None:
        if self._result is None:
            return
        self.app.push_screen(DiffModal(self._result.diff))

    def action_apply(self) -> None:
        if self._result is None or self._result.has_errors or not self._result.diff.changed:
            self.notify("Cannot apply: validation errors or no changes.", severity="error")
            return
        for patch in self._result.diff.patches:
            if not patch.changed:
                continue
            target = self._project_dir / patch.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(patch.after, encoding="utf-8")
        proposed = self._result.proposed
        if proposed is not None:
            from alloy_cli.core.events import record_event
            from alloy_cli.core.project import AlloyDir

            record_event(
                AlloyDir(root=self._project_dir),
                "peripheral_added",
                kind=proposed.kind,
                name=proposed.name,
            )
        self.notify("Applied.  Returning to Dashboard.", severity="information")
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_toggle_pinout_mode(self) -> None:
        widget = self.query_one("#peripheral-pinout", PinoutWidget)
        widget.toggle_mode()


def _resolve_device_for(config: ProjectConfig) -> DeviceIR | None:
    """Resolve the device IR from a board reference or a chip triple."""
    from alloy_cli.core import ir as _ir

    if config.chip is not None:
        try:
            return _ir.load_device(
                vendor=config.chip.vendor,
                family=config.chip.family,
                device=config.chip.device,
            )
        except (DeviceNotFoundError, DataRepoMissingError):
            return None
    if config.board is not None:
        from alloy_cli.core import boards as _boards

        try:
            manifest = _boards.lookup(config.board.id)
            return _ir.load_device(manifest.vendor, manifest.family, manifest.device)
        except (BoardNotFoundError, DeviceNotFoundError, DataRepoMissingError):
            return None
    return None


@register_screen(
    "peripheral-add",
    title="Add peripheral",
    description="IR-validated peripheral wiring (defaults to UART)",
)
def make_peripheral_add() -> Screen:
    return PeripheralAddScreen(kind=_DEFAULT_KIND, project_dir=Path.cwd())


__all__ = ["PeripheralAddScreen", "make_peripheral_add"]
