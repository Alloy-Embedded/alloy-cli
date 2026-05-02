"""``MemoryMapWidget`` — flash + RAM stacked-bar visualisation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static


@dataclass(frozen=True, slots=True)
class Section:
    """One ELF section row."""

    name: str
    region: str  # "flash" | "ram"
    size_bytes: int


@dataclass(frozen=True, slots=True)
class MemoryMap:
    flash_capacity: int
    ram_capacity: int
    sections: tuple[Section, ...]

    @property
    def flash_used(self) -> int:
        return sum(s.size_bytes for s in self.sections if s.region == "flash")

    @property
    def ram_used(self) -> int:
        return sum(s.size_bytes for s in self.sections if s.region == "ram")


def _bar(used: int, total: int, *, width: int = 30) -> str:
    if total <= 0:
        return "[" + " " * width + "]"
    pct = max(0.0, min(1.0, used / total))
    filled = int(pct * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {pct * 100:.0f}%"


class MemoryMapWidget(Widget):
    """Stacked-bar + section listing."""

    DEFAULT_CSS: ClassVar[str] = """
    MemoryMapWidget {
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self, memory: MemoryMap, *, name: str | None = None, id: str | None = None
    ) -> None:
        super().__init__(name=name, id=id)
        self._memory = memory

    @property
    def memory(self) -> MemoryMap:
        return self._memory

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(
                f"FLASH {self._memory.flash_used / 1024:.1f}/{self._memory.flash_capacity / 1024:.1f} KiB  "
                + _bar(self._memory.flash_used, self._memory.flash_capacity)
            )
            yield Static(
                f"RAM   {self._memory.ram_used / 1024:.1f}/{self._memory.ram_capacity / 1024:.1f} KiB  "
                + _bar(self._memory.ram_used, self._memory.ram_capacity)
            )
            yield Static("")
            yield Static("[bold]Sections[/bold]")
            if not self._memory.sections:
                yield Static("  [dim]No sections recorded.[/dim]")
                return
            for section in self._memory.sections:
                yield Static(f"  {section.region:<5} {section.name:<10} {section.size_bytes:>10} B")


def parse_size_lines(lines: Iterable[str]) -> tuple[Section, ...]:
    """Parse Berkeley ``size`` output into per-section :class:`Section` rows.

    The first non-header line is `text data bss dec hex filename`; we
    split that into three flash / ram-classified sections.  Used by
    tests + the screen.
    """
    rows: list[Section] = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 4:
            continue
        try:
            text = int(parts[0])
            data = int(parts[1])
            bss = int(parts[2])
        except ValueError:
            continue
        rows.extend(
            (
                Section(name=".text", region="flash", size_bytes=text),
                Section(name=".data", region="flash", size_bytes=data),
                Section(name=".bss", region="ram", size_bytes=bss),
            )
        )
        break
    return tuple(rows)


__all__ = ["MemoryMap", "MemoryMapWidget", "Section", "parse_size_lines"]
