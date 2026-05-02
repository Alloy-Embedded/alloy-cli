"""``ClockTreeScreen`` — interactive clock graph editor."""

from __future__ import annotations

import time
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Static

from alloy_cli.core import clocks as _clocks
from alloy_cli.core.diagnostics import UnifiedDiff
from alloy_cli.core.errors import ProjectConfigError
from alloy_cli.core.ir import DeviceIR
from alloy_cli.core.project import ProjectConfig
from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets.clock_tree import ClockTreeWidget, compute_rates, violations
from alloy_cli.tui.widgets.diff_widget import DiffModal

# Sentinel cycled through when the user has unsaved overrides.
_CUSTOM_LABEL = "(custom)"


class _ProfileNameModal(ModalScreen[str | None]):
    """Prompt for a profile name.

    Returns the entered string on Save, ``None`` on Cancel.  A
    blank name is treated as cancellation so the caller never has
    to special-case empty input.
    """

    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS: ClassVar[str] = """
    _ProfileNameModal {
        align: center middle;
    }
    #profile-name-modal {
        width: 60;
        height: auto;
        padding: 1 2;
        border: tall $primary;
        background: $surface;
    }
    #profile-name-actions {
        height: 3;
        align: right middle;
    }
    Button { margin: 0 1; }
    """

    def __init__(self, *, default: str = "", existing: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._default = default
        self._existing = set(existing)

    def compose(self) -> ComposeResult:
        with Vertical(id="profile-name-modal"):
            yield Static("[bold]Save clock profile[/bold]")
            yield Static("[dim]Letters / digits / underscores; must start with a letter.[/dim]")
            yield Input(
                value=self._default,
                placeholder="profile name",
                id="profile-name-input",
            )
            yield Static("", id="profile-name-error")
            with Horizontal(id="profile-name-actions"):
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._submit(self.query_one("#profile-name-input", Input).value)
        elif event.button.id == "cancel":
            self.dismiss(None)

    def _submit(self, raw: str) -> None:
        name = raw.strip()
        if not name:
            self._set_error("Name must not be empty.")
            return
        if name in self._existing:
            self._set_error(f"Profile {name!r} already exists.")
            return
        try:
            _clocks._validate_name(name)
        except _clocks.InvalidProfileNameError as exc:
            self._set_error(str(exc))
            return
        self.dismiss(name)

    def _set_error(self, message: str) -> None:
        self.query_one("#profile-name-error", Static).update(f"[red]{message}[/red]")

    def action_cancel(self) -> None:
        self.dismiss(None)


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
        self._profiles = self._collect_profiles(config)

    @staticmethod
    def _collect_profiles(config: ProjectConfig | None) -> tuple[str, ...]:
        if config is None:
            return ("default", _CUSTOM_LABEL)
        body = config.clocks.get("profiles") or {}
        if isinstance(body, dict):
            names = list(body.keys())
        else:
            names = []
        active = config.clocks.get("profile")
        if isinstance(active, str) and active not in names:
            names.append(active)
        if not names:
            names.append("default")
        names.append(_CUSTOM_LABEL)
        return tuple(names)

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
        if self._config is None:
            self.notify(
                "Saving profiles requires an open project.", severity="warning"
            )
            return
        widget = self.query_one("#clock-widget", ClockTreeWidget)
        overrides = dict(widget.overrides)
        if not overrides:
            self.notify(
                "No overrides to save — type a NODE=RATE entry first.",
                severity="warning",
            )
            return

        existing = tuple((self._config.clocks.get("profiles") or {}).keys())
        default_name = f"custom_{int(time.time())}"

        def _on_name(name: str | None) -> None:
            if name is None:
                return
            self._persist_profile(name, overrides)

        self.app.push_screen(
            _ProfileNameModal(default=default_name, existing=existing), _on_name
        )

    def _persist_profile(self, name: str, overrides: dict[str, int]) -> None:
        assert self._config is not None
        body = _clocks.profile_from_rates(overrides)
        try:
            diff = _clocks.save_profile(self._config, name, body)
        except _clocks.InvalidProfileNameError as exc:
            self.notify(str(exc), severity="error")
            return
        self.app.push_screen(
            DiffModal(diff, title=f"Save profile [bold]{name}[/bold]"),
            lambda applied: self._on_save_diff_applied(name, diff, applied),
        )

    def _on_save_diff_applied(
        self, name: str, diff: UnifiedDiff, applied: bool | None
    ) -> None:
        if not applied:
            return
        self._write_diff(diff)
        from alloy_cli.core.events import record_event
        from alloy_cli.core.project import AlloyDir

        record_event(AlloyDir(root=self._project_dir), "clock_profile_saved", name=name)
        # Refresh the in-screen profile rotation so `p` immediately
        # reflects the new entry.
        if self._config is not None:
            from alloy_cli.core.project import read

            try:
                self._config = read(self._project_dir / "alloy.toml")
            except (ProjectConfigError, OSError):
                pass
            self._profiles = self._collect_profiles(self._config)
            self._profile_index = self._profiles.index(name) if name in self._profiles else 0
            self.query_one("#clock-profile", Static).update(
                f"profile: [magenta]{self.current_profile}[/magenta]"
            )
        self.notify(f"Saved profile {name!r}.", severity="information")

    def _write_diff(self, diff: UnifiedDiff) -> None:
        for patch in diff.patches:
            if not patch.changed:
                continue
            target = self._project_dir / patch.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(patch.after, encoding="utf-8")


class _ClockTreePlaceholder(Screen[None]):
    """Surface when the registry factory is invoked without a project."""

    def compose(self) -> ComposeResult:
        yield Static("Clock Tree requires a project context.  Open it from the Dashboard.")


@register_screen("clock-tree", title="Clock Tree", description="Interactive clock graph")
def make_clock_tree() -> Screen:
    return _ClockTreePlaceholder()


__all__ = ["ClockTreeScreen", "make_clock_tree"]
