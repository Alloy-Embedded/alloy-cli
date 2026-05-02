"""``FlashScreen`` — live probe-rs progress + reset prompt."""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, ProgressBar, RichLog, Static

from alloy_cli.core import flash as _flash
from alloy_cli.core import process as _process
from alloy_cli.core.flash import FlashResult, ProbeInfo
from alloy_cli.core.project import ProjectConfig
from alloy_cli.tui.registry import register_screen

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


class _ResetPrompt(ModalScreen[bool]):
    """``Y/N`` prompt rendered after a successful flash."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Close"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    _ResetPrompt {
        align: center middle;
    }
    _ResetPrompt > Vertical {
        width: 50%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Reset target now?  [b]Y[/b] yes / [b]N[/b] no", id="reset-prompt")
            yield Button("Yes", id="yes", variant="success")
            yield Button("No", id="no", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self.action_confirm()
        elif event.button.id == "no":
            self.action_cancel()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class FlashScreen(Screen[FlashResult | None]):
    """Live progress bar + probe identity + reset prompt."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "cancel", "Close"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    FlashScreen #flash-root {
        padding: 0 1;
    }
    FlashScreen #flash-body {
        height: 1fr;
    }
    FlashScreen #flash-progress {
        margin: 1 0;
    }
    """

    def __init__(
        self,
        *,
        elf: Path,
        config: ProjectConfig,
        probe_kind: str = "auto",
        target: str | None = None,
        runner: _process.CommandRunner | None = None,
    ) -> None:
        super().__init__()
        self._elf = elf
        self._config = config
        self._probe_kind = probe_kind
        self._target = target
        self._runner = runner or _process.runner
        self._result: FlashResult | None = None
        self._reset_done = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="flash-root"):
            yield Static(f"[bold]Flashing[/bold] {self._elf.name}")
            yield Static("", id="flash-probe")
            yield Static(self._image_summary(), id="flash-image")
            yield ProgressBar(total=100.0, show_percentage=True, id="flash-progress")
            yield RichLog(id="flash-log", highlight=False, markup=False, max_lines=2_000)
            yield Static("", id="flash-status")
        yield Footer()

    def on_mount(self) -> None:
        self.set_timer(0.05, self._launch_flash)

    # ------------------------------------------------------------------
    # Flow
    # ------------------------------------------------------------------

    def _image_summary(self) -> str:
        try:
            size = self._elf.stat().st_size
        except OSError:
            size = -1
        return f"ELF size: {size} bytes"

    def _launch_flash(self) -> None:
        log = self.query_one("#flash-log", RichLog)
        progress = self.query_one("#flash-progress", ProgressBar)
        status = self.query_one("#flash-status", Static)

        def on_line(line: str) -> None:
            log.write(line)
            match = _PERCENT_RE.search(line)
            if match:
                try:
                    progress.update(progress=float(match.group(1)))
                except ValueError:
                    pass

        status.update("[yellow]running…[/yellow]")
        try:
            result = _flash.run(
                elf=self._elf,
                config=self._config,
                probe_kind=self._probe_kind,
                target=self._target,
                runner=self._runner,
                on_line=on_line,
                require_toolchain=False,
            )
        except Exception as exc:
            self._result = None
            status.update(f"[red]✗ {exc}[/red]\nRun `alloy doctor`.")
            return

        self._result = result
        self._render_probe(result.probe)
        if result.ok:
            progress.update(progress=100.0)
            status.update("[green]✓ Flash + verify OK[/green]")
            self.app.push_screen(_ResetPrompt(), self._on_reset_response)
        else:
            status.update(f"[red]✗ Flash failed (rc={result.returncode})[/red]")

    def _render_probe(self, probe: ProbeInfo) -> None:
        self.query_one("#flash-probe", Static).update(
            f"probe: [cyan]{probe.kind}[/cyan]  serial={probe.serial or '-'}  {probe.label}"
        )

    def _on_reset_response(self, confirmed: bool | None) -> None:
        if confirmed:
            # Best-effort reset via probe-rs — we surface failures inline.
            try:
                self._runner.run(["probe-rs", "reset"])
                self._reset_done = True
            except Exception as exc:
                self.notify(f"Reset failed: {exc}", severity="error")
        self.dismiss(self._result)

    def action_cancel(self) -> None:
        self.dismiss(self._result)

    @property
    def reset_done(self) -> bool:
        return self._reset_done


class _FlashPlaceholder(Screen[None]):
    """Surface when the registry factory is invoked without a project."""

    def compose(self) -> ComposeResult:
        yield Static("Flash requires a project context.  Open it from the Dashboard.")


@register_screen("flash", title="Flash", description="Live probe-rs flash + verify")
def make_flash() -> Screen:
    return _FlashPlaceholder()


__all__ = ["FlashScreen", "make_flash"]
