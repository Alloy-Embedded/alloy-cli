"""``BuildLogScreen`` — live cmake/ninja output + diagnostic navigator."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, RichLog, Static

from alloy_cli.core import build as _build
from alloy_cli.core import process as _process
from alloy_cli.core.build import BuildResult
from alloy_cli.core.diagnostic_parser import (
    CompilerDiagnostic,
    editor_command,
    parse_line,
)
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.tui.registry import register_screen


class BuildLogScreen(Screen[BuildResult | None]):
    """Live build log + parsed diagnostic navigator."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "cancel", "Close"),
        Binding("enter", "open_diag", "Open in editor", show=True),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    BuildLogScreen #build-root {
        padding: 0 1;
    }
    BuildLogScreen #build-body {
        height: 1fr;
    }
    BuildLogScreen #build-log {
        width: 70%;
        border: round $primary;
    }
    BuildLogScreen #build-diags {
        width: 30%;
        border: round $accent;
    }
    """

    def __init__(
        self,
        *,
        project_dir: Path,
        profile: _build.BuildProfile = "debug",
        runner: _process.CommandRunner | None = None,
        spawn_editor: Callable[[list[str]], None] | None = None,
    ) -> None:
        super().__init__()
        self._project_dir = project_dir.resolve()
        self._profile: _build.BuildProfile = profile
        self._runner = runner or _process.runner
        self._spawn_editor = spawn_editor or _default_spawn_editor
        self._diagnostics: list[CompilerDiagnostic] = []
        self._result: BuildResult | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="build-root"):
            yield Static(f"[bold]Building[/bold] [{self._profile}] {self._project_dir}")
            yield Static("Configure → Compile → Link", id="build-phase")
            with Horizontal(id="build-body"):
                yield RichLog(id="build-log", highlight=False, markup=False, max_lines=10_000)
                yield ListView(id="build-diags")
            yield Static("", id="build-status")
        yield Footer()

    def on_mount(self) -> None:
        # Defer build so the screen renders first.
        self.set_timer(0.05, self._launch_build)

    # ------------------------------------------------------------------
    # Build wiring
    # ------------------------------------------------------------------

    def _launch_build(self) -> None:
        log = self.query_one("#build-log", RichLog)

        def on_line(line: str) -> None:
            log.write(line)
            diag = parse_line(line)
            if diag is not None:
                self._diagnostics.append(diag)
                view = self.query_one("#build-diags", ListView)
                view.append(
                    ListItem(
                        Static(diag.label),
                        id=f"diag-{len(self._diagnostics)}",
                    )
                )

        self.query_one("#build-status", Static).update("[yellow]running…[/yellow]")
        try:
            result = _build.run(
                project_root=self._project_dir,
                profile=self._profile,
                runner=self._runner,
                on_line=on_line,
                require_toolchain=False,
            )
        except (AlloyCliError, OSError) as exc:
            self._result = None
            self.query_one("#build-status", Static).update(f"[red]{exc}[/red]")
            return
        self._result = result
        self._render_status(result)

    def _render_status(self, result: BuildResult) -> None:
        widget = self.query_one("#build-status", Static)
        if result.ok:
            widget.update(
                f"[green]✓ Build OK[/green]  cmake={result.cmake_returncode}  "
                f"ninja={result.build_returncode}  elf={result.elf_path or '-'}"
            )
        else:
            widget.update(
                f"[red]✗ Build failed[/red]  cmake={result.cmake_returncode}  "
                f"ninja={result.build_returncode}"
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_diag(self) -> None:
        view = self.query_one("#build-diags", ListView)
        idx = view.index
        if idx is None or idx < 0 or idx >= len(self._diagnostics):
            return
        diag = self._diagnostics[idx]
        editor = os.environ.get("EDITOR", "vi")
        if shutil.which(editor.split()[0]) is None:
            self.notify(
                f"$EDITOR ({editor}) is not on PATH; cannot open {diag.file}.",
                severity="error",
            )
            return
        self._spawn_editor(editor_command(diag, editor))

    def action_cancel(self) -> None:
        self.dismiss(self._result)


def _default_spawn_editor(argv: list[str]) -> None:
    import subprocess

    subprocess.Popen(argv).wait()


@register_screen("build-log", title="Build log", description="Streamed cmake + ninja output")
def make_build_log() -> Screen:
    return BuildLogScreen(project_dir=Path.cwd())


__all__ = ["BuildLogScreen", "make_build_log"]
