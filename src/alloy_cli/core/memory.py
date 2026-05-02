"""ELF memory summary — flash / RAM totals via ``arm-none-eabi-size``."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from alloy_cli.core import process


@dataclass(frozen=True, slots=True)
class MemoryReport:
    """Result of ``size --format=berkeley`` over a firmware ELF."""

    text_bytes: int
    data_bytes: int
    bss_bytes: int

    @property
    def flash_bytes(self) -> int:
        """Bytes that occupy flash: text + data."""
        return self.text_bytes + self.data_bytes

    @property
    def ram_bytes(self) -> int:
        """Bytes that occupy RAM at runtime: data + bss."""
        return self.data_bytes + self.bss_bytes


_BERKELEY_LINE = re.compile(
    r"^\s*(?P<text>\d+)\s+(?P<data>\d+)\s+(?P<bss>\d+)\s+\d+",
    re.MULTILINE,
)


def _resolve_size_binary() -> str | None:
    """Pick the best available ``size`` binary for embedded ELFs."""
    for candidate in ("arm-none-eabi-size", "size"):
        if shutil.which(candidate) is not None:
            return candidate
    return None


def parse_elf(elf: Path, *, runner: process.CommandRunner | None = None) -> MemoryReport | None:
    """Run ``size`` over ``elf`` and parse its Berkeley-format output.

    Returns ``None`` when no ``size`` binary is on PATH; lets callers
    keep going (with a "memory summary unavailable" hint) without
    refusing to build.
    """
    size_bin = _resolve_size_binary()
    if size_bin is None:
        return None
    r = runner or process.runner
    result = r.run([size_bin, "--format=berkeley", str(elf)])
    if not result.ok:
        return None
    match = _BERKELEY_LINE.search(result.stdout)
    if match is None:
        return None
    return MemoryReport(
        text_bytes=int(match.group("text")),
        data_bytes=int(match.group("data")),
        bss_bytes=int(match.group("bss")),
    )


def format_summary(report: MemoryReport) -> str:
    """Human-friendly one-liner: ``flash=12.3 KiB  ram=2.1 KiB``."""
    flash_kib = report.flash_bytes / 1024.0
    ram_kib = report.ram_bytes / 1024.0
    return (
        f"flash={flash_kib:.1f} KiB ({report.flash_bytes} B)  "
        f"ram={ram_kib:.1f} KiB ({report.ram_bytes} B)"
    )


__all__ = ["MemoryReport", "format_summary", "parse_elf"]
