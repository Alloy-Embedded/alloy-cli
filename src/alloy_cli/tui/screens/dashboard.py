"""Project Dashboard — the screen ``alloy`` (or ``alloy ui``) lands on."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core.project import PROJECT_FILE, AlloyDir, ProjectConfig, read
from alloy_cli.core.toolchain import ToolchainStatus  # type re-export only
from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.theme import GLYPH_FAIL, GLYPH_OK


@dataclass(frozen=True, slots=True)
class _BuildSummary:
    """Decoded ``.alloy/cache/last_build.json`` content."""

    profile: str
    ok: bool
    elf: str | None
    flash_bytes: int | None
    ram_bytes: int | None
    flash_capacity: int | None
    ram_capacity: int | None
    timestamp: str | None


def _read_build_summary(layout: AlloyDir) -> _BuildSummary | None:
    path = layout.cache / "last_build.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _BuildSummary(
        profile=str(payload.get("profile", "?")),
        ok=bool(payload.get("ok")),
        elf=payload.get("elf"),
        flash_bytes=payload.get("flash_bytes"),
        ram_bytes=payload.get("ram_bytes"),
        flash_capacity=payload.get("flash_capacity"),
        ram_capacity=payload.get("ram_capacity"),
        timestamp=payload.get("timestamp"),
    )


def _read_events(layout: AlloyDir, limit: int = 5) -> tuple[str, ...]:
    path = layout.cache / "events.jsonl"
    if not path.exists():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return ()
    out: list[str] = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue
        timestamp = record.get("timestamp", "?")
        event = record.get("event", "?")
        # Surface the most identifying field from the payload — for
        # peripheral_added that's `name`, for build_finished it's
        # the profile, etc.  Falling back to the empty string keeps
        # records without a payload readable.
        payload = record.get("payload") or {}
        tail = ""
        for key in ("name", "profile", "component", "device"):
            if key in payload:
                tail = f"  {key}={payload[key]}"
                break
        out.append(f"{timestamp}  {event}{tail}")
    return tuple(out)


def _toolchain_summary() -> tuple[ToolchainStatus, ...]:
    # Module-relative lookups so tests can stub _toolchain.detect_*
    # without rebinding the dashboard module's locals.
    return (
        _toolchain.detect_arm_gcc(),
        _toolchain.detect_cmake(),
        _toolchain.detect_probe_rs(),
    )


def _render_status_pill(status: ToolchainStatus) -> str:
    glyph = GLYPH_OK if status.present else GLYPH_FAIL
    body = f"{status.name}"
    if status.present and status.version:
        body += f" {status.version}"
    return f"{glyph} {body}"


def _render_memory_bar(used: int | None, total: int | None, label: str) -> str:
    """Render a 20-cell █/░ bar with `used / total KiB` summary."""
    if used is None or total is None or total == 0:
        return f"{label:<6} [dim]?[/dim]"
    pct = max(0.0, min(1.0, used / total))
    fill = int(pct * 20)
    bar = "█" * fill + "░" * (20 - fill)
    return f"{label:<6} [{bar}] {used / 1024:.1f}/{total / 1024:.1f} KiB ({pct * 100:.0f}%)"


class DashboardScreen(Screen):
    """Information-dense status view — Screen 1 from ``docs/TUI_DESIGN.md``."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("b", "noop('build')", "Build"),
        Binding("f", "noop('flash')", "Flash"),
        # `d` opens the new DoctorScreen (replaces the placeholder
        # "debug" no-op that wave-1 shipped).
        Binding("d", "doctor", "Doctor"),
        Binding("a", "noop('add')", "Add"),
        Binding("c", "noop('clocks')", "Clocks"),
        Binding("m", "noop('memory')", "Memory"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    DashboardScreen Vertical {
        padding: 0 1;
    }
    DashboardScreen .panel {
        height: auto;
        padding: 0 1;
        border-top: solid $primary;
    }
    DashboardScreen .panel-title {
        text-style: bold;
        color: $accent;
    }
    """

    def __init__(self, project_dir: Path) -> None:
        super().__init__()
        self._project_dir = project_dir.resolve()
        self._config: ProjectConfig | None = None
        self._error: str | None = None
        try:
            self._config = read(self._project_dir / PROJECT_FILE)
        except Exception as exc:
            self._error = str(exc)

    # --- composition ---------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            if self._error is not None:
                yield Static(f"[red]Could not read alloy.toml:[/red] {self._error}")
                yield Footer()
                return
            assert self._config is not None
            yield from self._compose_top_bar(self._config)
            yield from self._compose_peripherals(self._config)
            yield from self._compose_build()
            yield from self._compose_memory()
            yield from self._compose_activity()
            yield Static(
                "[dim]Hotkeys: b build, f flash, d doctor, a add, c clocks, m memory, "
                "Ctrl+P palette[/dim]",
                classes="panel",
            )
        yield Footer()

    def _compose_top_bar(self, config: ProjectConfig) -> ComposeResult:
        target = (
            f"board=[cyan]{config.board.id}[/cyan]"
            if config.board is not None
            else (
                f"chip=[cyan]{config.chip.vendor}/{config.chip.family}/{config.chip.device}[/cyan]"
                if config.chip is not None
                else "[red]no target[/red]"
            )
        )
        clock = config.clocks.get("profile") or "-"
        with Horizontal(classes="panel"):
            yield Static(f"[bold]{config.project.name}[/bold]  {target}", classes="panel-title")
            yield Static(f"  clock=[magenta]{clock}[/magenta]")
        # Toolchain pills render on a single row.  We render them as one
        # joined string rather than 3 Statics so Textual's Horizontal
        # auto-sizing doesn't squash the trailing pills off-screen.
        pills = "  ".join(_render_status_pill(s) for s in _toolchain_summary())
        yield Static(f"  {pills}", classes="panel", id="dash-toolchain")

    def _compose_peripherals(self, config: ProjectConfig) -> ComposeResult:
        with Vertical(classes="panel", id="dash-peripherals"):
            yield Static("Peripherals", classes="panel-title")
            if not config.peripherals:
                yield Static("  No peripherals yet.  Press 'a' to add one.")
                return
            for entry in config.peripherals:
                pins = " ".join(
                    f"{key}={value}"
                    for key in ("pin", "tx", "rx", "sda", "scl", "sck", "miso", "mosi")
                    for value in [entry.payload.get(key)]
                    if isinstance(value, str) and value
                )
                inst = entry.payload.get("peripheral")
                tail = f" ({inst})" if inst else ""
                yield Static(f"  {GLYPH_OK} {entry.kind:<7} {entry.name:<14}{tail}  {pins}")

    def _compose_build(self) -> ComposeResult:
        layout = AlloyDir(root=self._project_dir)
        summary = _read_build_summary(layout)
        with Vertical(classes="panel", id="dash-build"):
            yield Static("Build", classes="panel-title")
            if summary is None:
                yield Static("  Never built.  Press 'b'.")
                return
            glyph = GLYPH_OK if summary.ok else GLYPH_FAIL
            yield Static(
                f"  {glyph} profile={summary.profile}  elf={summary.elf or '-'}  "
                f"ts={summary.timestamp or '-'}"
            )

    def _compose_memory(self) -> ComposeResult:
        layout = AlloyDir(root=self._project_dir)
        summary = _read_build_summary(layout)
        with Vertical(classes="panel", id="dash-memory"):
            yield Static("Memory", classes="panel-title")
            if summary is None:
                yield Static("  [dim]No build yet.[/dim]")
                return
            yield Static(
                "  " + _render_memory_bar(summary.flash_bytes, summary.flash_capacity, "FLASH")
            )
            yield Static("  " + _render_memory_bar(summary.ram_bytes, summary.ram_capacity, "RAM"))

    def _compose_activity(self) -> ComposeResult:
        layout = AlloyDir(root=self._project_dir)
        events = _read_events(layout)
        with Vertical(classes="panel", id="dash-activity"):
            yield Static("Recent activity", classes="panel-title")
            if not events:
                yield Static("  [dim]No events recorded yet.[/dim]")
                return
            for line in events:
                yield Static(f"  {line}")

    # --- actions -------------------------------------------------------

    def action_noop(self, _hint: str) -> None:
        # Hotkeys are wired through to Phase-3 sub-screens once they
        # land.  Today we surface a notification so the binding is
        # discoverable without crashing.
        self.notify(
            f"'{_hint}' will jump to its dedicated screen once the next OpenSpec lands.",
            severity="information",
        )

    def action_doctor(self) -> None:
        """Open the interactive doctor screen."""
        # Imported lazily — keeps dashboard.py free of a hard
        # dependency on the doctor screen + its DataTable widget.
        from alloy_cli.tui.screens.doctor import DoctorScreen

        self.app.push_screen(DoctorScreen(project_dir=self._project_dir))


@register_screen(
    "dashboard",
    title="Dashboard",
    description="Status overview for the current project",
)
def make_dashboard() -> Screen:
    """Factory used by the command palette + ``alloy ui``."""
    return DashboardScreen(project_dir=Path.cwd())


__all__ = ["DashboardScreen", "make_dashboard"]
