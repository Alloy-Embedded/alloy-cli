"""``ClockTreeScreen`` — interactive clock graph editor."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from alloy_cli.core.ir import DeviceIR
from alloy_cli.core.project import ProjectConfig
from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets.clock_tree import ClockTreeWidget, compute_rates, violations


class ClockTreeScreen(Screen[None]):
    """Live clock graph + override editor."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Close"),
        Binding("p", "next_profile", "Profile"),
        Binding("ctrl+s", "save_profile", "Save profile"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    ClockTreeScreen #clock-root {
        padding: 0 1;
    }
    """

    def __init__(
        self,
        *,
        ir: DeviceIR,
        config: ProjectConfig | None = None,
        device_max_hz: int | None = None,
        project_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._ir = ir
        self._config = config
        self._device_max_hz = device_max_hz
        self._project_dir = project_dir or Path.cwd()
        self._profile_index = 0
        self._profiles = self._collect_profiles(config) if config is not None else ("default",)

    @staticmethod
    def _collect_profiles(config: ProjectConfig) -> tuple[str, ...]:
        names = list(config.clocks.get("profiles", []) or [])
        active = config.clocks.get("profile")
        if isinstance(active, str) and active not in names:
            names.append(active)
        return tuple(names) or ("default",)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="clock-root"):
            yield Static(
                f"[bold]Clock graph[/bold] for {self._ir.identity.device}",
            )
            with Horizontal():
                yield Static(
                    f"profile: [magenta]{self.current_profile}[/magenta]", id="clock-profile"
                )
                yield Static("  [dim]p cycle profile · Ctrl+S save[/dim]")
            yield ClockTreeWidget(
                self._ir,
                device_max_hz=self._device_max_hz,
                id="clock-widget",
            )
            yield Static("", id="clock-validation")
            with Horizontal():
                yield Input(
                    placeholder="override node_id=rate_hz (e.g. SYSCLK=128000000)",
                    id="clock-override",
                )
        yield Footer()

    @property
    def current_profile(self) -> str:
        if not self._profiles:
            return "default"
        return self._profiles[self._profile_index % len(self._profiles)]

    # ------------------------------------------------------------------
    # Events / actions
    # ------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "clock-override":
            return
        text = event.value.strip()
        if "=" not in text:
            self.notify("Use NODE=RATE format (e.g. SYSCLK=128000000).", severity="error")
            return
        node_id, rate = text.split("=", 1)
        try:
            value = int(rate.strip())
        except ValueError:
            self.notify(f"Rate must be an integer Hz: {rate!r}", severity="error")
            return
        widget = self.query_one("#clock-widget", ClockTreeWidget)
        widget.set_override(node_id.strip(), value)
        self._refresh_validation()

    def _refresh_validation(self) -> None:
        widget = self.query_one("#clock-widget", ClockTreeWidget)
        rates = compute_rates(self._ir, overrides=widget.overrides)
        bad = (
            violations(self._ir, rates, self._device_max_hz)
            if self._device_max_hz is not None
            else ()
        )
        text = (
            f"[red]✗ {len(bad)} bus rate violation(s): {', '.join(bad)}[/red]"
            if bad
            else "[green]✓ All rates within device limits.[/green]"
        )
        self.query_one("#clock-validation", Static).update(text)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_next_profile(self) -> None:
        self._profile_index = (self._profile_index + 1) % len(self._profiles)
        self.query_one("#clock-profile", Static).update(
            f"profile: [magenta]{self.current_profile}[/magenta]"
        )

    def action_save_profile(self) -> None:
        self.notify(
            "Saving custom profiles to alloy.toml lands together with the codegen "
            "PLL algebra.  Today the override stays in-screen.",
            severity="information",
        )


class _ClockTreePlaceholder(Screen[None]):
    """Surface when the registry factory is invoked without a project."""

    def compose(self) -> ComposeResult:
        yield Static("Clock Tree requires a project context.  Open it from the Dashboard.")


@register_screen("clock-tree", title="Clock Tree", description="Interactive clock graph")
def make_clock_tree() -> Screen:
    return _ClockTreePlaceholder()


__all__ = ["ClockTreeScreen", "make_clock_tree"]
