"""Tests for the Wave-4 MCP probe tools (Wave 4 group 6).

Pinned scenarios (lifted from ``mcp-surface/spec.md``):

- All six tools register in the default registry + appear in
  ``ToolRegistry.names()``.
- ``probe_reset`` happy path returns the typed JSON envelope.
- ``probe_reset`` with no probe attached raises typed envelope.
- ``probe_reset`` with multiple probes raises typed envelope listing
  every probe.
- ``probe_erase_plan`` returns the JSON projection.
- ``probe_erase`` without ``confirm=True`` raises
  ``family-toolchain-erase-confirmation-required``.
- ``probe_erase`` with ``confirm=True`` dispatches.
- ``probe_monitor_{open, poll, close}`` form a working session.
- Idle session timeout auto-closes.
- Every tool's response is JSON-serialisable.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pytest

from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.process import FakeRunner
from alloy_cli.mcp import ToolError, ToolRegistry, build_default_registry
from alloy_cli.mcp.tools import _MONITOR_SESSIONS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stlink(serial: str = "AAA") -> _po.ProbeIdentity:
    return _po.ProbeIdentity(
        vid="0483",
        pid="374b",
        serial=serial,
        kind="stlink",
        vendor_only=False,
    )


@pytest.fixture
def registry(tmp_path: Path) -> ToolRegistry:
    return build_default_registry(project_dir=tmp_path, runner=FakeRunner())


@pytest.fixture
def fake_probe(monkeypatch: pytest.MonkeyPatch) -> _po.FakeProbe:
    """Inject a single attached probe + a FakeProbe backend."""
    probe = _stlink()
    monkeypatch.setattr(_po, "_list_probes", lambda *, project_root=None: (probe,))
    fp = _po.FakeProbe(identity=probe)
    monkeypatch.setattr(
        _po,
        "real_probe_for",
        lambda identity, *, project_root=None, runner=None: fp,
    )
    return fp


@pytest.fixture(autouse=True)
def _clear_monitor_sessions() -> None:
    """Reset the process-global session table between tests."""
    _MONITOR_SESSIONS._sessions.clear()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_every_probe_tool_registers(registry: ToolRegistry) -> None:
    names = registry.names()
    for tool in (
        "probe_reset",
        "probe_erase_plan",
        "probe_erase",
        "probe_monitor_open",
        "probe_monitor_poll",
        "probe_monitor_close",
    ):
        assert tool in names, f"{tool!r} not registered"


# ---------------------------------------------------------------------------
# probe_reset
# ---------------------------------------------------------------------------


def test_probe_reset_happy_path(registry: ToolRegistry, fake_probe) -> None:
    payload = registry.call("probe_reset")
    assert payload["method"] == "soft"
    assert payload["halt_after"] is False
    assert payload["probe"]["kind"] == "stlink"
    assert "duration_ms" in payload
    assert len(fake_probe.reset_calls) == 1


def test_probe_reset_hard_method(registry: ToolRegistry, fake_probe) -> None:
    payload = registry.call("probe_reset", method="hard", halt_after=True)
    assert payload["method"] == "hard"
    assert payload["halt_after"] is True
    assert fake_probe.reset_calls[0].method == "hard"


def test_probe_reset_invalid_method(registry: ToolRegistry, fake_probe) -> None:
    with pytest.raises(ToolError) as excinfo:
        registry.call("probe_reset", method="warm")
    assert excinfo.value.error_type == "family-toolchain-probe-error"


def test_probe_reset_no_probe_attached(registry: ToolRegistry, monkeypatch) -> None:
    monkeypatch.setattr(_po, "_list_probes", lambda *, project_root=None: ())
    with pytest.raises(ToolError) as excinfo:
        registry.call("probe_reset")
    assert excinfo.value.error_type == "family-toolchain-probe-not-attached"
    assert excinfo.value.detail is not None
    assert excinfo.value.detail.get("detected_probes") == []


def test_probe_reset_multiple_probes(registry: ToolRegistry, monkeypatch) -> None:
    a = _stlink("AAA")
    b = _stlink("BBB")
    monkeypatch.setattr(_po, "_list_probes", lambda *, project_root=None: (a, b))
    with pytest.raises(ToolError) as excinfo:
        registry.call("probe_reset")
    err = excinfo.value
    assert err.error_type == "family-toolchain-probe-multiple-attached"
    assert err.detail is not None
    serials = {p["serial"] for p in err.detail.get("detected_probes") or ()}
    assert serials == {"AAA", "BBB"}


# ---------------------------------------------------------------------------
# probe_erase_plan
# ---------------------------------------------------------------------------


def test_probe_erase_plan_returns_chip_wide_default(registry: ToolRegistry, fake_probe) -> None:
    payload = registry.call("probe_erase_plan")
    assert payload["probe"]["kind"] == "stlink"
    assert len(payload["regions"]) == 1
    assert payload["regions"][0]["name"] == "all"


def test_probe_erase_plan_literal_range(registry: ToolRegistry, fake_probe) -> None:
    payload = registry.call("probe_erase_plan", regions=["0x08000000-0x08010000"])
    assert len(payload["regions"]) == 1
    assert payload["regions"][0]["base"] == 0x0800_0000
    assert payload["regions"][0]["size"] == 0x10000


# ---------------------------------------------------------------------------
# probe_erase (two-phase)
# ---------------------------------------------------------------------------


def test_probe_erase_without_confirm_raises_typed(registry: ToolRegistry, fake_probe) -> None:
    with pytest.raises(ToolError) as excinfo:
        registry.call("probe_erase")
    assert excinfo.value.error_type == "family-toolchain-erase-confirmation-required"


def test_probe_erase_with_confirm_dispatches(registry: ToolRegistry, fake_probe) -> None:
    payload = registry.call("probe_erase", confirm=True)
    assert payload["probe"]["kind"] == "stlink"
    assert payload["total_bytes_erased"] >= 0
    assert "duration_ms" in payload
    assert len(fake_probe.erase_calls) == 1


def test_probe_erase_propagates_typed_backend_error(registry: ToolRegistry, monkeypatch) -> None:
    from alloy_cli.core.errors import FamilyToolchainEraseProbeFailedError

    probe = _stlink()
    monkeypatch.setattr(_po, "_list_probes", lambda *, project_root=None: (probe,))
    fp = _po.FakeProbe(identity=probe)
    fp.fail_next_erase(
        FamilyToolchainEraseProbeFailedError(
            "checksum mismatch",
            stderr="probe-rs: ERR_CHECKSUM",
            returncode=2,
        )
    )
    monkeypatch.setattr(
        _po,
        "real_probe_for",
        lambda identity, *, project_root=None, runner=None: fp,
    )
    with pytest.raises(ToolError) as excinfo:
        registry.call("probe_erase", confirm=True)
    err = excinfo.value
    assert err.error_type == "family-toolchain-erase-probe-failed"
    assert err.detail is not None
    assert err.detail.get("returncode") == 2
    assert "ERR_CHECKSUM" in (err.detail.get("stderr") or "")


# ---------------------------------------------------------------------------
# probe_monitor_{open, poll, close}
# ---------------------------------------------------------------------------


def test_probe_monitor_open_returns_session_id(registry: ToolRegistry, fake_probe) -> None:
    payload = registry.call(
        "probe_monitor_open",
        port="/dev/cu.usbmodem1234",
        baud=115200,
    )
    assert "session_id" in payload
    assert isinstance(payload["session_id"], str) and len(payload["session_id"]) >= 16
    assert payload["port"] == "/dev/cu.usbmodem1234"
    assert payload["baud"] == 115200
    assert payload["mode"] == "raw"


def test_probe_monitor_open_raw_requires_port(registry: ToolRegistry, fake_probe) -> None:
    """Raw mode without a port is a clean error rather than a crash."""
    with pytest.raises(ToolError) as excinfo:
        registry.call("probe_monitor_open", mode="raw")
    assert excinfo.value.error_type == "family-toolchain-probe-error"


def test_probe_monitor_poll_returns_incremental_bytes(registry: ToolRegistry, fake_probe) -> None:
    open_payload = registry.call(
        "probe_monitor_open",
        port="/dev/cu.usbmodem1234",
    )
    sid = open_payload["session_id"]
    # Inject bytes via the session table directly (the Wave-4 streaming
    # backend isn't wired yet; the MCP tool only owns the session
    # plumbing).
    _MONITOR_SESSIONS.append_bytes(sid, b"hello world\n")
    poll = registry.call("probe_monitor_poll", session_id=sid)
    assert poll["new_bytes"] == "hello world\n"
    assert poll["total_bytes"] == 12
    assert poll["closed"] is False
    # Subsequent poll returns nothing (no new bytes).
    poll2 = registry.call("probe_monitor_poll", session_id=sid)
    assert poll2["new_bytes"] == ""
    assert poll2["total_bytes"] == 12


def test_probe_monitor_close_returns_summary(registry: ToolRegistry, fake_probe) -> None:
    open_payload = registry.call("probe_monitor_open", port="/dev/cu.usbmodem1234")
    sid = open_payload["session_id"]
    _MONITOR_SESSIONS.append_bytes(sid, b"line one\nline two\n")
    summary = registry.call("probe_monitor_close", session_id=sid)
    assert summary["closed"] is True
    assert summary["total_bytes"] == 18
    assert summary["last_line"] == "line two"


def test_probe_monitor_poll_after_close_raises_typed(registry: ToolRegistry, fake_probe) -> None:
    open_payload = registry.call("probe_monitor_open", port="/dev/cu.usbmodem1234")
    sid = open_payload["session_id"]
    registry.call("probe_monitor_close", session_id=sid)
    with pytest.raises(ToolError) as excinfo:
        registry.call("probe_monitor_poll", session_id=sid)
    assert excinfo.value.error_type == "probe-operation-cancelled"


# ---------------------------------------------------------------------------
# JSON serialisability
# ---------------------------------------------------------------------------


def test_every_probe_tool_response_is_json_serialisable(registry: ToolRegistry, fake_probe) -> None:
    samples = [
        registry.call("probe_reset"),
        registry.call("probe_erase_plan"),
        registry.call("probe_erase", confirm=True),
        registry.call("probe_monitor_open", port="/dev/cu.test"),
    ]
    for payload in samples:
        blob = _json.dumps(payload, sort_keys=True)
        assert _json.loads(blob) == payload


def test_system_prompt_documents_probe_two_phase_pattern() -> None:
    """The opencode system prompt mentions the probe tools + the
    two-phase pattern for ``probe_erase``.  Keeps LLM agents aware
    of the safety contract."""
    prompt = (
        Path(__file__).resolve().parents[1] / "src/alloy_cli/integrations/opencode/system_prompt.md"
    ).read_text(encoding="utf-8")
    assert "probe_reset" in prompt
    assert "probe_erase_plan" in prompt
    assert "probe_erase" in prompt
    assert "probe_monitor_open" in prompt
    assert "confirm=true" in prompt or "confirm=True" in prompt
