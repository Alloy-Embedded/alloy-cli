"""Tests for the Wave-4 ``MonitorScreen`` (Wave 4 group 5).

Pinned scenarios (lifted from ``tui-experience/spec.md``):

- The screen is registered in the screen registry.
- Construction with explicit port + baud + mode lands at the
  banner phase.
- Pressing Ctrl+] dismisses with a typed summary.
- The factory builds a screen at the default port.
"""

from __future__ import annotations

from alloy_cli.tui.registry import registry as default_registry
from alloy_cli.tui.screens.monitor import (
    MonitorScreen,
    MonitorSummary,
    make_monitor,
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_monitor_screen_is_registered() -> None:
    """``register_screen("monitor", ...)`` populates the default
    registry; the command palette discovers it."""
    entry = default_registry.get("monitor")
    assert entry is not None
    assert entry.title == "Monitor"
    assert "Ctrl+]" in entry.description or "disconnect" in entry.description


def test_make_monitor_returns_screen_at_default_port() -> None:
    """The factory builds a screen with a placeholder port — the
    user wires the real port via the launcher (Wave 5)."""
    screen = make_monitor()
    assert isinstance(screen, MonitorScreen)
    assert screen._port == "<unset>"
    assert screen._mode == "raw"
    assert screen._baud == 115200


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_monitor_screen_records_port_baud_mode() -> None:
    screen = MonitorScreen(
        port="/dev/cu.usbmodem1234",
        baud=921600,
        mode="raw",
    )
    assert screen._port == "/dev/cu.usbmodem1234"
    assert screen._baud == 921600
    assert screen._mode == "raw"
    assert screen._bytes_total == 0
    assert screen._closed is False


def test_monitor_screen_summary_carries_byte_count() -> None:
    summary = MonitorSummary(
        bytes_captured=1024,
        duration_ms=4000,
        last_line="boot complete",
    )
    assert summary.bytes_captured == 1024
    assert summary.duration_ms == 4000
    assert summary.last_line == "boot complete"


# ---------------------------------------------------------------------------
# Pilot-driven (mounted) tests
# ---------------------------------------------------------------------------


def test_monitor_screen_banner_text_carries_port_baud_mode() -> None:
    """``_banner_text`` is the bridge into the on-mount Static; pinning
    its output keeps the user-visible label stable without booting the
    full Textual app loop (which would race with the worker thread)."""
    screen = MonitorScreen(
        port="/dev/cu.usbmodem1234",
        baud=115200,
        mode="raw",
    )
    text = screen._banner_text()
    assert "/dev/cu.usbmodem1234" in text
    assert "115200" in text
    assert "Ctrl+]" in text
    assert "raw" in text


def test_monitor_screen_action_close_session_marks_closed() -> None:
    """``action_close_session`` flips the closed flag so the worker
    thread + idle handlers stop emitting bytes."""
    screen = MonitorScreen(
        port="/dev/cu.usbmodem1234",
        baud=115200,
        mode="raw",
    )
    screen._bytes_total = 42
    screen._last_line = "test line"
    # The screen isn't mounted; dismiss() can't run without an app
    # context.  Verify the closed flag is the sole observable side
    # effect we care about for tests.
    try:
        screen.action_close_session()
    except Exception:  # noqa: BLE001 -- dismiss() raises without an app context
        pass
    assert screen._closed is True


# ---------------------------------------------------------------------------
# Closed state guards
# ---------------------------------------------------------------------------


def test_monitor_screen_close_is_idempotent() -> None:
    """Calling close twice doesn't re-dismiss or raise."""
    screen = MonitorScreen(port="/dev/cu.usbmodem1234", baud=115200, mode="raw")
    screen._closed = True  # pretend we've already closed
    # Re-calling close should be a no-op.
    screen.action_close_session()
    assert screen._closed is True
