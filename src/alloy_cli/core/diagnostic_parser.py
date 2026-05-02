"""Parse compiler diagnostics out of build log lines."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIAG_RE = re.compile(
    r"^(?P<file>[^\s:]+):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<severity>error|warning|note):\s*(?P<message>.+)$"
)


@dataclass(frozen=True, slots=True)
class CompilerDiagnostic:
    """One parsed compiler line."""

    file: str
    line: int
    col: int
    severity: str
    message: str

    @property
    def label(self) -> str:
        return f"{self.severity}: {self.file}:{self.line}:{self.col}: {self.message}"


def parse_line(text: str) -> CompilerDiagnostic | None:
    match = _DIAG_RE.match(text.strip())
    if not match:
        return None
    return CompilerDiagnostic(
        file=match.group("file"),
        line=int(match.group("line")),
        col=int(match.group("col")),
        severity=match.group("severity"),
        message=match.group("message").strip(),
    )


def editor_command(diag: CompilerDiagnostic, editor: str = "vi") -> list[str]:
    """Return an argv that opens the editor at the diagnostic location."""
    base = editor.split()
    return [*base, f"+{diag.line}:{diag.col}", diag.file]


__all__ = ["CompilerDiagnostic", "editor_command", "parse_line"]
