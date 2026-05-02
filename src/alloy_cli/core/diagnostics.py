"""Diagnostic + UnifiedDiff value types shared by peripheral operations."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One validation finding produced by a core operation.

    A non-empty list of ``error`` diagnostics MUST prevent the CLI
    from applying the change.  ``warning`` and ``info`` are advisory.
    """

    severity: Severity
    code: str
    message: str
    path: str | None = None  # JSON-pointer-ish location, e.g. "peripherals[0].tx"
    suggestions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FilePatch:
    """Unified-diff for a single file (text-addressable)."""

    path: Path
    before: str
    after: str

    def unified(self, *, context: int = 3) -> str:
        diff = difflib.unified_diff(
            self.before.splitlines(keepends=True),
            self.after.splitlines(keepends=True),
            fromfile=f"a/{self.path.as_posix()}",
            tofile=f"b/{self.path.as_posix()}",
            n=context,
        )
        return "".join(diff)

    @property
    def changed(self) -> bool:
        return self.before != self.after


@dataclass(frozen=True, slots=True)
class UnifiedDiff:
    """A bundle of :class:`FilePatch`es returned by every ``add_*`` op."""

    patches: tuple[FilePatch, ...]

    @property
    def changed(self) -> bool:
        return any(p.changed for p in self.patches)

    def render(self) -> str:
        chunks = [p.unified() for p in self.patches if p.changed]
        return "\n".join(chunks)


__all__ = [
    "Diagnostic",
    "FilePatch",
    "Severity",
    "UnifiedDiff",
]
