"""GDB MI2 adapter — typed wrapper over a ``gdb -i=mi2`` subprocess.

The DebugScreen mounts a :class:`GdbSession` against a freshly-spawned
``probe-rs gdb-server``.  Every method emits one MI2 command and
parses the wire-level response into a typed dataclass so the screen
never string-scrapes.

The MI2 wire format documented at
<https://sourceware.org/gdb/onlinedocs/gdb/GDB_002fMI-Output-Records.html>;
this module implements the subset alloy-cli needs (result records,
async records, console streams).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.log import get_logger

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GdbSessionError(AlloyCliError):
    """Raised when the MI2 wire returns ``^error`` or a parse fails."""

    error_type = "gdb-session-error"


# ---------------------------------------------------------------------------
# MI2 wire types
# ---------------------------------------------------------------------------


MiClass = Literal["done", "running", "stopped", "error", "exit", "console", "log", "target"]


@dataclass(frozen=True, slots=True)
class MiRecord:
    """One MI2 record parsed from the wire.

    ``cls`` is the result-class string (``done`` / ``running`` /
    ``stopped`` / ``error`` …).  ``payload`` is a flat dict of
    string keys; nested values stay as strings so the screen can
    decide how deeply to interpret them.
    """

    cls: MiClass
    payload: dict[str, str] = field(default_factory=dict)
    text: str = ""


@dataclass(frozen=True, slots=True)
class StopReason:
    """The most-recent ``*stopped`` record."""

    reason: str
    file: str | None = None
    line: int | None = None
    func: str | None = None
    bkpt_id: str | None = None


@dataclass(frozen=True, slots=True)
class Frame:
    level: int
    func: str
    file: str | None = None
    line: int | None = None
    addr: str | None = None


@dataclass(frozen=True, slots=True)
class Variable:
    name: str
    value: str


@dataclass(frozen=True, slots=True)
class Register:
    name: str
    value: str


@dataclass(frozen=True, slots=True)
class MemorySlice:
    address: str
    contents: tuple[int, ...]


# ---------------------------------------------------------------------------
# MI2 parser
# ---------------------------------------------------------------------------


_RESULT_RE = re.compile(r"^\^(?P<cls>done|running|connected|exit|error)(?:,(?P<payload>.*))?$")
_ASYNC_RE = re.compile(r"^\*(?P<cls>stopped|running)(?:,(?P<payload>.*))?$")
_CONSOLE_RE = re.compile(r'^~"(?P<text>.*)"$')
_LOG_RE = re.compile(r'^&"(?P<text>.*)"$')
_TARGET_RE = re.compile(r'^@"(?P<text>.*)"$')


def _parse_payload(raw: str) -> dict[str, str]:
    """Best-effort parse of a flat MI2 payload.

    Real MI2 output nests dicts arbitrarily deep; for the small
    subset we consume (frame info, breakpoint info, register
    values) the flat string-keyed dict is enough.  Anything more
    structured can layer on top later.
    """
    out: dict[str, str] = {}
    if not raw:
        return out
    # Split on top-level commas — this is naive but safe for the
    # subset of MI2 records we ingest.  A future iteration can
    # plug a proper LL parser if we ever need full nesting.
    depth = 0
    buf: list[str] = []
    chunks: list[str] = []
    in_string = False
    for ch in raw:
        if ch == '"' and (not buf or buf[-1] != "\\"):
            in_string = not in_string
        if not in_string:
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
            elif ch == "," and depth == 0:
                chunks.append("".join(buf))
                buf = []
                continue
        buf.append(ch)
    if buf:
        chunks.append("".join(buf))

    for chunk in chunks:
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        out[key] = value
    return out


def parse_mi2(line: str) -> MiRecord | None:
    """Parse a single MI2 line into an :class:`MiRecord`.

    Returns ``None`` for lines that are pure prompts (``(gdb) ``)
    or unrecognised noise; callers loop until they see a result
    record.
    """
    line = line.rstrip("\n")
    if not line or line == "(gdb)":
        return None
    if m := _RESULT_RE.match(line):
        cls = m.group("cls")
        payload = _parse_payload(m.group("payload") or "")
        return MiRecord(cls=cls, payload=payload, text=line)  # type: ignore[arg-type]
    if m := _ASYNC_RE.match(line):
        cls = m.group("cls")
        payload = _parse_payload(m.group("payload") or "")
        return MiRecord(cls=cls, payload=payload, text=line)  # type: ignore[arg-type]
    if m := _CONSOLE_RE.match(line):
        return MiRecord(cls="console", text=m.group("text"))
    if m := _LOG_RE.match(line):
        return MiRecord(cls="log", text=m.group("text"))
    if m := _TARGET_RE.match(line):
        return MiRecord(cls="target", text=m.group("text"))
    return None


# ---------------------------------------------------------------------------
# GdbSession
# ---------------------------------------------------------------------------


@dataclass
class GdbSession:
    """Active ``gdb -i=mi2`` session.

    The class owns a :class:`subprocess.Popen` whose stdin/stdout
    speak MI2.  Every ``cmd_*`` method writes one MI2 line and
    reads result records until it sees the synchronous reply.

    Tests inject a ``Popen``-like fake; production callers reach
    through :func:`launch`.
    """

    process: subprocess.Popen[str]
    elf_path: Path | None = None
    target_port: int = 1337
    log: list[MiRecord] = field(default_factory=list)
    _token: int = 0

    # Lifecycle ---------------------------------------------------------------

    def __enter__(self) -> GdbSession:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self._write("-gdb-exit\n")
                self.process.wait(timeout=2.0)
            except (subprocess.TimeoutExpired, BrokenPipeError, OSError):
                self.process.kill()

    # I/O ---------------------------------------------------------------------

    def _write(self, line: str) -> None:
        if self.process.stdin is None:
            raise GdbSessionError("gdb stdin pipe is not available")
        try:
            self.process.stdin.write(line)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise GdbSessionError(f"gdb stdin closed: {exc}") from exc

    def _read_until_result(self) -> MiRecord:
        """Read MI2 records until a result record (^done / ^error) shows up."""
        if self.process.stdout is None:
            raise GdbSessionError("gdb stdout pipe is not available")
        for raw in self.process.stdout:
            record = parse_mi2(raw)
            if record is None:
                continue
            self.log.append(record)
            if record.cls in ("done", "running", "connected", "exit", "error"):
                if record.cls == "error":
                    msg = record.payload.get("msg", "unknown gdb error")
                    raise GdbSessionError(msg)
                return record
        raise GdbSessionError("gdb subprocess closed before returning a result")

    def issue(self, command: str) -> MiRecord:
        """Send one MI2 command and return its synchronous result record."""
        self._token += 1
        self._write(command if command.endswith("\n") else command + "\n")
        return self._read_until_result()

    # High-level methods ------------------------------------------------------

    def connect_target(self, port: int) -> MiRecord:
        return self.issue(f"-target-select extended-remote :{port}")

    def load(self, elf_path: Path) -> MiRecord:
        self.elf_path = elf_path
        return self.issue(f"-file-exec-and-symbols {elf_path}")

    def set_breakpoint(self, location: str) -> MiRecord:
        return self.issue(f"-break-insert {location}")

    def delete_breakpoint(self, bkpt_id: str) -> MiRecord:
        return self.issue(f"-break-delete {bkpt_id}")

    def continue_(self) -> MiRecord:
        return self.issue("-exec-continue")

    def step(self) -> MiRecord:
        return self.issue("-exec-step")

    def next(self) -> MiRecord:
        return self.issue("-exec-next")

    def finish(self) -> MiRecord:
        return self.issue("-exec-finish")

    def interrupt(self) -> MiRecord:
        return self.issue("-exec-interrupt --all")

    def eval(self, expression: str) -> str:
        record = self.issue(f"-data-evaluate-expression {expression}")
        return record.payload.get("value", "")


# ---------------------------------------------------------------------------
# Process launch helpers
# ---------------------------------------------------------------------------


def launch(
    *,
    gdb_binary: str = "arm-none-eabi-gdb",
    elf_path: Path | None = None,
    target_port: int = 1337,
    extra_args: Iterable[str] = (),
) -> GdbSession:
    """Spawn ``gdb -i=mi2`` and return an attached :class:`GdbSession`."""
    args: list[str] = [gdb_binary, "-i=mi2", "--quiet"]
    args.extend(extra_args)
    if elf_path is not None:
        args.append(str(elf_path))
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    session = GdbSession(process=proc, elf_path=elf_path, target_port=target_port)
    # Drain the banner so the next read_until_result sees a fresh
    # exchange.  We don't error on the banner because GDB's first
    # output line varies by version.
    try:
        session._read_until_result()
    except GdbSessionError as exc:
        _log.debug("gdb banner read returned: %s", exc)
    return session


__all__ = [
    "Frame",
    "GdbSession",
    "GdbSessionError",
    "MemorySlice",
    "MiClass",
    "MiRecord",
    "Register",
    "StopReason",
    "Variable",
    "launch",
    "parse_mi2",
]
