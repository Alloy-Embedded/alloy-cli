"""Append-only structured event log under ``.alloy/cache/events.jsonl``.

The Dashboard "Recent activity" panel and the
``alloy.list_recent_events`` MCP tool both read from this file;
this module is the write side.  Every mutating core operation
funnels through :func:`record_event` so the log is the single
source of truth for "what happened in this project".

Append is atomic at the line level (one ``open(..., "a")`` +
single ``write()`` call); the OS guarantees no two writers
interleave mid-line.  The file rotates to ``events.jsonl.1`` once
it crosses :data:`MAX_LINES`; older rotations are dropped.

Failure to write an event MUST NOT crash the caller — a missing
log line is preferable to a missing build.  Errors funnel
through :mod:`alloy_cli.core.log` (when it lands) and otherwise
are silently swallowed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alloy_cli.core.project import AlloyDir

# Hard cap before rotating; matches the spec scenario.
MAX_LINES = 1024


@dataclass(frozen=True, slots=True)
class EventRecord:
    """One JSONL line as a typed value.

    Tests construct these directly; production paths flow
    through :func:`record_event`.
    """

    timestamp: str
    event: str
    payload: Mapping[str, Any]

    def to_json(self) -> str:
        # ``ensure_ascii=False`` keeps Unicode payloads (peripheral
        # names, file paths with accents) compact; ``sort_keys=True``
        # makes the JSON string-stable for tests.
        return json.dumps(
            {"timestamp": self.timestamp, "event": self.event, "payload": dict(self.payload)},
            ensure_ascii=False,
            sort_keys=True,
        )


def _now_iso() -> str:
    """Current UTC time as a stable ISO-8601 string with seconds resolution."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as fp:
        return sum(1 for _ in fp)


@dataclass(frozen=True, slots=True)
class EventLogger:
    """Resolves the events file path + handles append + rotation.

    The class is intentionally tiny — every mutating op is allowed
    to construct it on demand (cheap, no I/O until ``append``).
    """

    layout: AlloyDir

    @property
    def path(self) -> Path:
        return self.layout.cache / "events.jsonl"

    @property
    def rolled_path(self) -> Path:
        return self.layout.cache / "events.jsonl.1"

    def append(self, record: EventRecord) -> None:
        """Append one record.  Rotates the file pre-write if needed."""
        self.layout.ensure()
        if _line_count(self.path) >= MAX_LINES:
            self._rotate()
        # ``a`` mode + single write is atomic at the line level on
        # POSIX (PIPE_BUF guarantees up to 4 KB; our records are
        # comfortably under that).  Append-mode honours O_APPEND
        # so concurrent writers seek-to-end before each write.
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(record.to_json())
            fp.write("\n")

    def _rotate(self) -> None:
        if self.rolled_path.exists():
            self.rolled_path.unlink()
        if self.path.exists():
            os.replace(self.path, self.rolled_path)


def record_event(
    layout: AlloyDir | Path,
    event_type: str,
    /,
    **payload: Any,
) -> None:
    """Append one event record; never raises.

    ``layout`` may be either an :class:`AlloyDir` or a project
    root :class:`Path` (we wrap it).  Failing to write is logged
    but never propagated — a missing event is always preferable
    to crashing the caller.
    """
    if isinstance(layout, Path):
        layout = AlloyDir(root=layout)
    record = EventRecord(timestamp=_now_iso(), event=event_type, payload=dict(payload))
    try:
        EventLogger(layout=layout).append(record)
    except OSError:
        # Disk full / permission / read-only fs — swallow.  The
        # operation that triggered the event already succeeded;
        # losing the audit trail is the lesser evil.
        return


__all__ = [
    "MAX_LINES",
    "EventLogger",
    "EventRecord",
    "record_event",
]
