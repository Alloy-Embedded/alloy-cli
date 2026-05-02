"""Tests for the MI2 wire parser + :class:`GdbSession` (#31).

These tests exercise the parsing layer in isolation; the
:class:`subprocess.Popen` interaction is verified via a small
fake (no real ``arm-none-eabi-gdb`` is invoked).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from alloy_cli.core.gdb import (
    GdbSession,
    GdbSessionError,
    parse_mi2,
)

# ---------------------------------------------------------------------------
# parse_mi2
# ---------------------------------------------------------------------------


def test_parse_done_record() -> None:
    record = parse_mi2('^done,bkpt={number="3",type="breakpoint"}')
    assert record is not None
    assert record.cls == "done"
    # Top-level payload key is `bkpt`; nested values stay as strings.
    assert "bkpt" in record.payload


def test_parse_running_record() -> None:
    record = parse_mi2("^running")
    assert record is not None
    assert record.cls == "running"
    assert record.payload == {}


def test_parse_error_record_extracts_message() -> None:
    record = parse_mi2('^error,msg="No symbol \'foo\' in current context."')
    assert record is not None
    assert record.cls == "error"
    assert "No symbol" in record.payload["msg"]


def test_parse_async_stopped_record() -> None:
    record = parse_mi2(
        '*stopped,reason="breakpoint-hit",bkptno="2",frame={'
        'file="main.c",line="42",func="main"}'
    )
    assert record is not None
    assert record.cls == "stopped"
    assert record.payload["reason"] == "breakpoint-hit"


def test_parse_console_record_extracts_text() -> None:
    record = parse_mi2('~"hello world\\n"')
    assert record is not None
    assert record.cls == "console"
    assert "hello world" in record.text


def test_parse_log_record() -> None:
    record = parse_mi2('&"warning: foo"')
    assert record is not None
    assert record.cls == "log"
    assert "warning" in record.text


def test_parse_returns_none_for_prompt() -> None:
    assert parse_mi2("(gdb)") is None
    assert parse_mi2("") is None


def test_parse_returns_none_for_unrecognised_line() -> None:
    assert parse_mi2("this is not a real MI line") is None


# ---------------------------------------------------------------------------
# GdbSession against a fake subprocess
# ---------------------------------------------------------------------------


@dataclass
class _FakePopen:
    """A subprocess.Popen-shaped fake driving canned MI2 output."""

    stdout_lines: list[str] = field(default_factory=list)
    stdin_buffer: io.StringIO = field(default_factory=io.StringIO)
    poll_value: int | None = None

    def __post_init__(self) -> None:
        self.stdout = iter(self.stdout_lines)
        self.stdin = self.stdin_buffer

    def poll(self) -> int | None:
        return self.poll_value

    def wait(self, timeout: float | None = None) -> int:
        return self.poll_value or 0

    def kill(self) -> None:
        self.poll_value = -9


def _make_session(stdout: Iterable[str]) -> GdbSession:
    proc = _FakePopen(stdout_lines=[*stdout, "(gdb)\n"])
    return GdbSession(process=proc)  # type: ignore[arg-type]


def test_issue_returns_done_record() -> None:
    session = _make_session(["^done\n"])
    record = session.issue("-target-select extended-remote :1337")
    assert record.cls == "done"
    # The session's log retains the parsed record for the panel.
    assert any(r.cls == "done" for r in session.log)


def test_issue_raises_on_error_record() -> None:
    session = _make_session(['^error,msg="symbol not found"\n'])
    with pytest.raises(GdbSessionError) as exc_info:
        session.issue("-data-evaluate-expression foo")
    assert "symbol not found" in str(exc_info.value)


def test_issue_writes_command_to_stdin() -> None:
    session = _make_session(["^done\n"])
    session.issue("-exec-step")
    assert session.process.stdin.getvalue().strip() == "-exec-step"  # type: ignore[union-attr]


def test_set_breakpoint_returns_payload() -> None:
    session = _make_session(['^done,bkpt={number="2",file="main.c",line="42"}\n'])
    record = session.set_breakpoint("main.c:42")
    assert record.cls == "done"
    assert "bkpt" in record.payload


def test_continue_step_next_finish_use_correct_mi_commands() -> None:
    for method, expected_cmd in (
        (lambda s: s.continue_(), "-exec-continue"),
        (lambda s: s.step(), "-exec-step"),
        (lambda s: s.next(), "-exec-next"),
        (lambda s: s.finish(), "-exec-finish"),
    ):
        session = _make_session(["^running\n"])
        method(session)
        assert session.process.stdin.getvalue().strip() == expected_cmd  # type: ignore[union-attr]


def test_eval_returns_payload_value() -> None:
    session = _make_session(['^done,value="42"\n'])
    out = session.eval("foo")
    assert out == "42"


def test_load_records_elf_path(tmp_path: Path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    session = _make_session(["^done\n"])
    session.load(elf)
    assert session.elf_path == elf


def test_session_close_writes_gdb_exit() -> None:
    proc = _FakePopen(stdout_lines=[])
    proc.poll_value = None  # still running so close() writes
    session = GdbSession(process=proc)  # type: ignore[arg-type]
    session.close()
    assert "-gdb-exit" in proc.stdin_buffer.getvalue()


def test_session_close_on_dead_process_is_noop() -> None:
    proc = _FakePopen(stdout_lines=[])
    proc.poll_value = 0  # already exited
    session = GdbSession(process=proc)  # type: ignore[arg-type]
    session.close()  # MUST NOT raise


def test_session_context_manager_closes_on_exit() -> None:
    proc = _FakePopen(stdout_lines=[])
    proc.poll_value = None
    with GdbSession(process=proc) as session:  # type: ignore[arg-type]
        assert session.process is proc
    assert "-gdb-exit" in proc.stdin_buffer.getvalue()
