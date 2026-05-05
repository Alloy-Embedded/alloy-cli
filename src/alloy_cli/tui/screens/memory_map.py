"""``MemoryMapScreen`` — flash + RAM stacked-bar visualisation."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli.tui.registry import register_screen
from alloy_cli.tui.widgets.memory_map import MemoryMap, MemoryMapWidget


class MemoryMapScreen(Screen[None]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Close")]

    DEFAULT_CSS: ClassVar[str] = """
    MemoryMapScreen #memory-root {
        padding: 0 1;
    }
    """

    def __init__(self, *, memory: MemoryMap) -> None:
        super().__init__()
        self._memory = memory

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="memory-root"):
            yield Static("[bold]Memory map[/bold]")
            yield MemoryMapWidget(self._memory, id="memory-widget")
        yield Footer()

    def action_cancel(self) -> None:
        self.dismiss(None)


class _MemoryMapPlaceholder(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Static("Memory map requires a build artefact.  Run [bold]alloy build[/bold] first.")


def _find_elf(project_root: Path) -> Path | None:
    """Return the most-recently modified ELF in .alloy/build/, or None."""
    build_dir = project_root / ".alloy" / "build"
    if not build_dir.is_dir():
        return None
    elfs = list(build_dir.glob("*.elf"))
    if not elfs:
        return None
    return max(elfs, key=lambda p: p.stat().st_mtime)


def _size_sections(elf: Path) -> tuple:
    """Run `arm-none-eabi-size` (or `size`) and parse Berkeley output."""
    from alloy_cli.tui.widgets.memory_map import parse_size_lines

    for candidate in ("arm-none-eabi-size", "size"):
        if shutil.which(candidate) is None:
            continue
        try:
            result = subprocess.run(
                [candidate, str(elf)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            sections = parse_size_lines(result.stdout.splitlines())
            if sections:
                return sections
        except Exception:  # noqa: BLE001 -- size tool may not exist / timeout / output garbage; try next candidate
            continue
    return ()


def _capacities_from_config(config: object | None) -> tuple[int, int]:
    """Return (flash_bytes, ram_bytes) from board.json or alloy.toml chip entry."""
    if config is None:
        return 0, 0
    from alloy_cli.core import boards as _boards
    from alloy_cli.core.errors import BoardNotFoundError

    try:
        board = getattr(config, "board", None)
        if board is not None:
            manifest = _boards.lookup(board.id)
            flash = manifest.flash_size_bytes
            ram = int(manifest.payload.get("sram_size_bytes", 0))
            return flash, ram
    except BoardNotFoundError:
        pass
    return 0, 0


@register_screen("memory-map", title="Memory map", description="Flash + RAM usage")
def make_memory_map() -> Screen:
    """Build a live MemoryMapScreen from the most-recent ELF in .alloy/build/.

    Falls back to the placeholder when no ELF exists yet.
    """
    from alloy_cli.core.errors import AlloyCliError
    from alloy_cli.core.project import PROJECT_FILE, read as _read_project
    from alloy_cli.tui.widgets.memory_map import MemoryMap

    # --- Locate project root (walk up from CWD) ---
    cwd = Path(os.getcwd()).resolve()
    config = None
    project_root = cwd
    for parent in [cwd, *cwd.parents]:
        toml = parent / PROJECT_FILE
        if toml.exists():
            try:
                config = _read_project(toml)
                project_root = parent
            except AlloyCliError:
                pass
            break

    # --- Locate ELF ---
    elf = _find_elf(project_root)
    if elf is None:
        return _MemoryMapPlaceholder()

    # --- Parse sections + capacities ---
    sections = _size_sections(elf)
    flash_capacity, ram_capacity = _capacities_from_config(config)

    memory = MemoryMap(
        flash_capacity=flash_capacity,
        ram_capacity=ram_capacity,
        sections=sections,
    )
    return MemoryMapScreen(memory=memory)


__all__ = ["MemoryMapScreen", "make_memory_map"]
