"""End-to-end tests for ``alloy monitor`` (Wave 4 group 4).

Pinned scenarios (lifted from ``cli-surface/spec.md``):

- ``--port`` + ``--baud`` opens the explicit port outside a project.
- Auto-detect via ``alloy.toml [uart].debug`` works inside a project.
- Missing port + no project config exits with a clear error.
- Ctrl+] (simulated by the orchestrator raising
  ``ProbeOperationCancelledError``) prints the summary line + exits 0.
- ``--mode rtt`` dispatches the RTT path.
- ``--ansi`` controls escape-sequence pass-through.
- ``--help`` advertises every flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import ProbeOperationCancelledError
from alloy_cli.core.project import (
    SCHEMA_VERSION,
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stub_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scripted_events: list[_po.MonitorEvent] | None = None,
    raise_on_open: Exception | None = None,
) -> dict:
    """Replace ``select_probe`` + ``real_probe_for`` + ``open_monitor`` with
    recorders.  Returns the captured-state dict."""
    captured: dict = {"open_calls": []}

    fake_probe = _po.FakeProbe(scripted_monitor_events=scripted_events or [])

    monkeypatch.setattr(
        _po,
        "select_probe",
        lambda *, hint=None, project_root=None, probes=None: fake_probe.identity,
    )
    monkeypatch.setattr(
        _po,
        "real_probe_for",
        lambda identity, *, project_root=None, runner=None: fake_probe,
    )

    original_open = _po.open_monitor

    def _record_open(probe, *, port, baud, mode, on_event):
        captured["open_calls"].append({"port": port, "baud": baud, "mode": mode})
        if raise_on_open is not None:
            raise raise_on_open
        return original_open(probe, port=port, baud=baud, mode=mode, on_event=on_event)

    monkeypatch.setattr(_po, "open_monitor", _record_open)

    captured["fake_probe"] = fake_probe
    return captured


def _seed_uart_project(project_root: Path, *, baud: int) -> None:
    """Drop an alloy.toml with a console UART peripheral.

    The schema requires ``peripheral`` / ``tx`` / ``rx`` for UART
    entries; we add ``baud`` as an extra field the schema validator
    accepts (additional properties are permitted).
    """
    project_root.mkdir(parents=True, exist_ok=True)
    config = ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name="fixture"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(
            PeripheralEntry(
                kind="uart",
                name="console",
                payload={
                    "peripheral": "USART2",
                    "tx": "PA2",
                    "rx": "PA3",
                    "baud": baud,
                },
            ),
        ),
        build={},
        flash={},
        raw={},
    )
    write(project_root / "alloy.toml", config)


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_monitor_help_lists_every_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["monitor", "--help"])
    assert result.exit_code == 0
    for flag in ("--port", "--baud", "--mode", "--ansi", "--probe", "--project-dir"):
        assert flag in result.output


# ---------------------------------------------------------------------------
# Port resolution
# ---------------------------------------------------------------------------


def test_monitor_explicit_port_and_baud(tmp_path, monkeypatch) -> None:
    """``--port`` + ``--baud`` works outside a project."""
    captured = _stub_orchestrator(
        monkeypatch,
        scripted_events=[
            _po.MonitorBytes(chunk=b"hello\n", timestamp_ms=0),
        ],
    )
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            [
                "monitor",
                "--port",
                "/dev/cu.usbmodem1234",
                "--baud",
                "115200",
                "--project-dir",
                cwd,
            ],
        )
    assert result.exit_code == 0, result.output
    assert "hello" in result.output
    call = captured["open_calls"][0]
    assert call["port"] == Path("/dev/cu.usbmodem1234")
    assert call["baud"] == 115200
    assert call["mode"] == "raw"


def test_monitor_resolves_debug_baud_from_project_config(tmp_path, monkeypatch) -> None:
    """Inside a project with a console UART declaring ``baud``, the
    monitor picks up the rate.  The port path always requires ``--port``
    (Wave 4 does not autodetect OS-level serial paths)."""
    captured = _stub_orchestrator(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        _seed_uart_project(Path(cwd), baud=921600)
        result = runner.invoke(
            cli,
            ["monitor", "--port", "/dev/cu.test", "--project-dir", cwd],
        )
    assert result.exit_code == 0, result.output
    call = captured["open_calls"][0]
    assert call["baud"] == 921600


def test_monitor_explicit_baud_overrides_project_config(tmp_path, monkeypatch) -> None:
    """``--baud`` wins over the project's UART baud config."""
    captured = _stub_orchestrator(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        _seed_uart_project(Path(cwd), baud=115200)
        result = runner.invoke(
            cli,
            [
                "monitor",
                "--port",
                "/dev/cu.test",
                "--baud",
                "230400",
                "--project-dir",
                cwd,
            ],
        )
    assert result.exit_code == 0, result.output
    call = captured["open_calls"][0]
    assert call["baud"] == 230400


def test_monitor_no_port_and_no_config_exits_with_clear_error(tmp_path, monkeypatch) -> None:
    """Outside a project + no ``--port`` → exit non-zero."""
    _stub_orchestrator(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["monitor", "--project-dir", cwd])
    assert result.exit_code != 0
    assert "--port" in result.output
    assert "[uart].debug" in result.output or "alloy.toml" in result.output


def test_monitor_default_baud_is_115200(tmp_path, monkeypatch) -> None:
    """When neither ``--baud`` nor the project config resolves, default
    falls back to 115200."""
    captured = _stub_orchestrator(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["monitor", "--port", "/dev/cu.test", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert captured["open_calls"][0]["baud"] == 115200


# ---------------------------------------------------------------------------
# Cancellation contract
# ---------------------------------------------------------------------------


def test_monitor_ctrl_close_prints_summary_and_exits_zero(tmp_path, monkeypatch) -> None:
    """ProbeOperationCancelledError → exit 0 + one-line summary."""
    cancel = ProbeOperationCancelledError(
        "User pressed Ctrl+].",
        duration_ms=4720,
        bytes_captured=124,
        last_line="boot complete",
    )
    _stub_orchestrator(monkeypatch, raise_on_open=cancel)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["monitor", "--port", "/dev/cu.test", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert "Closed monitor session" in result.output
    assert "124 bytes" in result.output
    assert "4.7s" in result.output
    assert "boot complete" in result.output


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


def test_monitor_rtt_mode_dispatches_through_select_probe(tmp_path, monkeypatch) -> None:
    """``--mode rtt`` requires probe selection (raw mode does not)."""
    captured = _stub_orchestrator(monkeypatch)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            [
                "monitor",
                "--mode",
                "rtt",
                "--probe",
                "0483:374b:AAA",
                "--port",
                "/dev/cu.test",  # ignored in rtt mode but Click requires SOME port for raw default
                "--project-dir",
                cwd,
            ],
        )
    assert result.exit_code == 0, result.output
    assert captured["open_calls"][0]["mode"] == "rtt"


def test_monitor_ansi_strip_default(tmp_path, monkeypatch) -> None:
    """ANSI escape sequences are stripped by default."""
    _stub_orchestrator(
        monkeypatch,
        scripted_events=[
            _po.MonitorBytes(
                chunk=b"\x1b[32mhello\x1b[0m\n",
                timestamp_ms=0,
            ),
        ],
    )
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["monitor", "--port", "/dev/cu.test", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert "hello" in result.output
    # The 0x1b escape should NOT appear in the rendered output.
    assert "\x1b[32m" not in result.output


def test_monitor_ansi_passthrough(tmp_path, monkeypatch) -> None:
    """``--ansi`` keeps escape sequences intact."""
    _stub_orchestrator(
        monkeypatch,
        scripted_events=[
            _po.MonitorBytes(
                chunk=b"\x1b[32mhello\x1b[0m\n",
                timestamp_ms=0,
            ),
        ],
    )
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            ["monitor", "--ansi", "--port", "/dev/cu.test", "--project-dir", cwd],
        )
    assert result.exit_code == 0, result.output
    assert "\x1b[32m" in result.output
