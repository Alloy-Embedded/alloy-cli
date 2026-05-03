"""Tests for the Wave-4 ``core.probe_orchestrator`` module.

Pinned scenarios (lifted from the spec):

- Probe selection: single-attached fast path; multiple-attached
  raises typed envelope listing every probe; vendor-only probe
  raises ``family-toolchain-probe-unauthorised``.
- ``reset_target`` returns a ``ResetReport`` with the right method.
- ``plan_erase`` resolves named regions via the IR resolver
  callback; unsupported aliases raise typed envelope with
  ``known_regions``.
- ``plan_erase`` accepts literal ``0xBASE-0xEND`` ranges.
- ``execute_erase`` reports total bytes erased + duration.
- ``open_monitor`` pumps events in order to the callback.
- ``FakeProbe`` records every call faithfully.
- ``MonitorSessionTable`` enforces idle timeout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import (
    FamilyToolchainEraseUnsupportedRegionError,
    FamilyToolchainProbeMultipleAttachedError,
    FamilyToolchainProbeNotAttachedError,
    FamilyToolchainProbeUnauthorisedError,
    ProbeOperationCancelledError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stlink(serial: str = "0671FF1234") -> _po.ProbeIdentity:
    return _po.ProbeIdentity(
        vid="0483",
        pid="374b",
        serial=serial,
        kind="stlink",
        vendor_only=False,
    )


def _jlink_vendor_only() -> _po.ProbeIdentity:
    return _po.ProbeIdentity(
        vid="1366",
        pid="0101",
        serial="000123456789",
        kind="jlink",
        vendor_only=True,
    )


# ---------------------------------------------------------------------------
# Probe selection
# ---------------------------------------------------------------------------


def test_select_probe_single_attached_returns_it() -> None:
    sole = _stlink()
    chosen = _po.select_probe(probes=(sole,))
    assert chosen is sole


def test_select_probe_no_attached_raises_typed_envelope() -> None:
    with pytest.raises(FamilyToolchainProbeNotAttachedError) as excinfo:
        _po.select_probe(probes=())
    assert excinfo.value.error_type == "family-toolchain-probe-not-attached"


def test_select_probe_multiple_attached_lists_them() -> None:
    a = _stlink("AAA")
    b = _stlink("BBB")
    with pytest.raises(FamilyToolchainProbeMultipleAttachedError) as excinfo:
        _po.select_probe(probes=(a, b))
    err = excinfo.value
    assert err.error_type == "family-toolchain-probe-multiple-attached"
    serials = {row[2] for row in err.detected}
    assert serials == {"AAA", "BBB"}


def test_select_probe_hint_disambiguates() -> None:
    a = _stlink("AAA")
    b = _stlink("BBB")
    chosen = _po.select_probe(hint="0483:374b:AAA", probes=(a, b))
    assert chosen.serial == "AAA"


def test_select_probe_partial_hint_matches_vid() -> None:
    a = _stlink("AAA")
    b = _po.ProbeIdentity(vid="1366", pid="0101", serial="BBB", kind="jlink", vendor_only=False)
    chosen = _po.select_probe(hint="0483", probes=(a, b))
    assert chosen.serial == "AAA"


def test_select_probe_hint_no_match_raises_not_attached() -> None:
    a = _stlink("AAA")
    with pytest.raises(FamilyToolchainProbeNotAttachedError):
        _po.select_probe(hint="dead:beef:none", probes=(a,))


def test_select_probe_vendor_only_raises_unauthorised() -> None:
    sole = _jlink_vendor_only()
    with pytest.raises(FamilyToolchainProbeUnauthorisedError) as excinfo:
        _po.select_probe(probes=(sole,))
    err = excinfo.value
    assert err.error_type == "family-toolchain-probe-unauthorised"
    assert err.vendor_tool == "J-Link Commander"


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def test_reset_target_returns_typed_report() -> None:
    fake = _po.FakeProbe()
    report = _po.reset_target(fake, method="soft", halt_after=False)
    assert isinstance(report, _po.ResetReport)
    assert report.method == "soft"
    assert report.halt_after is False
    assert report.duration_ms > 0


def test_reset_target_records_call_on_fake() -> None:
    fake = _po.FakeProbe()
    _po.reset_target(fake, method="hard", halt_after=True)
    assert len(fake.reset_calls) == 1
    assert fake.reset_calls[0].method == "hard"
    assert fake.reset_calls[0].halt_after is True


def test_reset_target_rejects_unknown_method() -> None:
    fake = _po.FakeProbe()
    with pytest.raises(ValueError):
        _po.reset_target(fake, method="warm")


def test_reset_target_propagates_typed_failure() -> None:
    fake = _po.FakeProbe()
    boom = FamilyToolchainProbeNotAttachedError("probe vanished mid-reset")
    fake.fail_next_reset(boom)
    with pytest.raises(FamilyToolchainProbeNotAttachedError):
        _po.reset_target(fake, method="soft")


# ---------------------------------------------------------------------------
# Erase plan / execute
# ---------------------------------------------------------------------------


def test_plan_erase_with_no_regions_returns_chip_wide_plan() -> None:
    fake = _po.FakeProbe()
    plan = _po.plan_erase(fake, regions=None, all_size_bytes=128 * 1024)
    assert len(plan.regions) == 1
    assert plan.regions[0].name == "all"
    assert plan.regions[0].size == 128 * 1024
    assert plan.total_bytes == 128 * 1024


def test_plan_erase_with_alias_uses_region_resolver() -> None:
    fake = _po.FakeProbe()

    def _resolver(name: str) -> _po.EraseRegion:
        if name == "bootloader":
            return _po.EraseRegion(name="bootloader", base=0x0800_0000, size=0x4000)
        raise KeyError(("bootloader", "appslot-a"))

    plan = _po.plan_erase(fake, regions=["bootloader"], region_resolver=_resolver)
    assert len(plan.regions) == 1
    assert plan.regions[0].name == "bootloader"
    assert plan.regions[0].base == 0x0800_0000
    assert plan.regions[0].size == 0x4000


def test_plan_erase_unknown_alias_raises_typed_with_known_regions() -> None:
    fake = _po.FakeProbe()

    def _resolver(name: str) -> _po.EraseRegion:
        raise KeyError(("bootloader", "appslot-a"))

    with pytest.raises(FamilyToolchainEraseUnsupportedRegionError) as excinfo:
        _po.plan_erase(fake, regions=["wat"], region_resolver=_resolver)
    err = excinfo.value
    assert err.error_type == "family-toolchain-erase-unsupported-region"
    assert err.known_regions == ("bootloader", "appslot-a")


def test_plan_erase_alias_without_resolver_raises_typed() -> None:
    fake = _po.FakeProbe()
    with pytest.raises(FamilyToolchainEraseUnsupportedRegionError):
        _po.plan_erase(fake, regions=["bootloader"])


def test_plan_erase_accepts_literal_range() -> None:
    fake = _po.FakeProbe()
    plan = _po.plan_erase(fake, regions=["0x08000000-0x08010000"])
    assert len(plan.regions) == 1
    assert plan.regions[0].base == 0x0800_0000
    assert plan.regions[0].size == 0x10000


def test_plan_erase_rejects_inverted_range() -> None:
    fake = _po.FakeProbe()
    with pytest.raises(FamilyToolchainEraseUnsupportedRegionError):
        _po.plan_erase(fake, regions=["0x08010000-0x08000000"])


def test_execute_erase_returns_typed_report() -> None:
    fake = _po.FakeProbe()
    plan = _po.plan_erase(fake, regions=["0x08000000-0x08010000"])
    report = _po.execute_erase(fake, plan)
    assert isinstance(report, _po.EraseReport)
    assert report.total_bytes_erased == 0x10000
    assert len(fake.erase_calls) == 1
    assert fake.erase_calls[0].regions == plan.regions


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


def test_open_monitor_pumps_events_in_order() -> None:
    fake = _po.FakeProbe()
    fake.script_monitor_events(
        [
            _po.MonitorOpened(
                probe=fake.identity,
                port="/dev/cu.usbmodem1234",
                baud=115200,
                mode="raw",
                started_at_ms=0,
            ),
            _po.MonitorBytes(chunk=b"boot complete\n", timestamp_ms=10),
            _po.MonitorBytes(chunk=b"hello world\n", timestamp_ms=12),
            _po.MonitorClosed(duration_ms=12, bytes_captured=27, last_line="hello world"),
        ]
    )

    received: list[_po.MonitorEvent] = []
    bytes_seen = _po.open_monitor(
        fake,
        port=Path("/dev/cu.usbmodem1234"),
        baud=115200,
        mode="raw",
        on_event=received.append,
    )
    assert bytes_seen == len(b"boot complete\n") + len(b"hello world\n")
    kinds = [type(e).__name__ for e in received]
    assert kinds == ["MonitorOpened", "MonitorBytes", "MonitorBytes", "MonitorClosed"]


def test_open_monitor_rejects_invalid_mode() -> None:
    fake = _po.FakeProbe()
    with pytest.raises(ValueError):
        _po.open_monitor(fake, port=None, baud=115200, mode="raw-jr", on_event=lambda _e: None)


# ---------------------------------------------------------------------------
# MonitorSessionTable
# ---------------------------------------------------------------------------


def test_monitor_session_open_returns_uuid() -> None:
    table = _po.MonitorSessionTable()
    sid = table.open(_stlink())
    assert isinstance(sid, str) and len(sid) >= 16
    assert table.active_count() == 1


def test_monitor_session_poll_returns_incremental_bytes() -> None:
    table = _po.MonitorSessionTable()
    sid = table.open(_stlink())
    table.append_bytes(sid, b"first chunk\n")
    poll = table.poll(sid)
    assert poll["new_bytes"] == "first chunk\n"
    assert poll["total_bytes"] == 12
    assert poll["closed"] is False
    table.append_bytes(sid, b"second\n")
    poll2 = table.poll(sid)
    assert poll2["new_bytes"] == "second\n"
    assert poll2["total_bytes"] == 19


def test_monitor_session_close_returns_summary() -> None:
    table = _po.MonitorSessionTable()
    sid = table.open(_stlink())
    table.append_bytes(sid, b"hello\nworld\n")
    summary = table.close(sid)
    assert summary["closed"] is True
    assert summary["total_bytes"] == 12
    # ``last_line`` is the most recent complete line — the bytes
    # between the second-to-last and last newline.
    assert summary["last_line"] == "world"


def test_monitor_session_poll_after_close_raises_typed() -> None:
    table = _po.MonitorSessionTable()
    sid = table.open(_stlink())
    table.close(sid)
    with pytest.raises(ProbeOperationCancelledError) as excinfo:
        table.poll(sid)
    assert excinfo.value.error_type == "probe-operation-cancelled"


def test_monitor_session_idle_timeout_auto_closes() -> None:
    table = _po.MonitorSessionTable(idle_timeout_seconds=0.001)
    sid = table.open(_stlink())
    import time as _t

    _t.sleep(0.05)
    with pytest.raises(ProbeOperationCancelledError):
        table.poll(sid)


def test_monitor_session_unknown_id_raises_typed() -> None:
    table = _po.MonitorSessionTable()
    with pytest.raises(ProbeOperationCancelledError):
        table.poll("not-a-real-session")


# ---------------------------------------------------------------------------
# UI-free invariant
# ---------------------------------------------------------------------------


def test_orchestrator_module_is_ui_free() -> None:
    """No Click / Rich / Textual / ``input()`` / ``sys.stdin`` reach
    can land in ``probe_orchestrator.py`` — the AST contract test
    covers the broader entry-point invariant; this one pins the
    module itself."""
    import ast
    import inspect

    source = inspect.getsource(_po)
    tree = ast.parse(source)
    forbidden_imports = {"click", "rich", "textual"}

    def _module_root(name: str) -> str:
        return name.split(".", 1)[0]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _module_root(alias.name)
                assert root not in forbidden_imports, (
                    f"probe_orchestrator must not import {alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = _module_root(node.module)
            assert root not in forbidden_imports, (
                f"probe_orchestrator must not import from {node.module!r}"
            )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "input":
                raise AssertionError(
                    "probe_orchestrator must not call `input()` — UI shells own user prompts."
                )
            if isinstance(func, ast.Attribute):
                # Walk attribute chain looking for ``sys.stdin``
                cur: ast.AST = func
                parts: list[str] = []
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                if "stdin" in parts and "sys" in parts:
                    raise AssertionError(
                        "probe_orchestrator must not read sys.stdin — UI shells own input."
                    )
