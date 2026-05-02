"""End-to-end tests for ``alloy add ...`` Click commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import ir as _ir
from alloy_cli.core.ir import (
    ConnectionCandidateView,
    DeviceIdentity,
    DeviceIR,
    PeripheralView,
    PinView,
)
from alloy_cli.core.project import (
    PROJECT_FILE,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    read,
    write,
)
from alloy_cli.main import cli


def _seed_project(root: Path) -> None:
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    write(root / PROJECT_FILE, config)


def _ir_fixture() -> DeviceIR:
    return DeviceIR(
        identity=DeviceIdentity(
            vendor="st",
            family="stm32g0",
            device="stm32g071rb",
            package="lqfp64",
            core="cortex-m0plus",
            summary="STM32G0",
        ),
        peripherals=(
            PeripheralView(name="USART1", ip_name="uart", ip_version=None, base_address=0),
            PeripheralView(name="USART2", ip_name="uart", ip_version=None, base_address=0),
        ),
        pins=(
            PinView(name="PA2", port="A", number=2),
            PinView(name="PA3", port="A", number=3),
            PinView(name="PA9", port="A", number=9),
            PinView(name="PA10", port="A", number=10),
            PinView(name="PA5", port="A", number=5),
        ),
        connection_candidates=(
            ConnectionCandidateView(pin="PA9", peripheral="USART1", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA10", peripheral="USART1", signal="RX", af_number=1),
            ConnectionCandidateView(pin="PA2", peripheral="USART2", signal="TX", af_number=1),
            ConnectionCandidateView(pin="PA3", peripheral="USART2", signal="RX", af_number=1),
        ),
        dma_routes=(),
        clock_nodes=(),
        payload={},
    )


@pytest.fixture
def patched_ir(monkeypatch):
    """Patch ``core.ir.load_device`` to return our synthetic IR."""
    fixture = _ir_fixture()
    monkeypatch.setattr(_ir, "load_device", lambda *a, **kw: fixture)
    yield fixture


# ---------------------------------------------------------------------------
# Help / surface
# ---------------------------------------------------------------------------


def test_alloy_add_lists_kinds() -> None:
    result = CliRunner().invoke(cli, ["add", "--help"])
    assert result.exit_code == 0
    for kind in ("uart", "gpio", "spi", "i2c"):
        assert kind in result.output


def test_alloy_add_uart_help_shows_options() -> None:
    result = CliRunner().invoke(cli, ["add", "uart", "--help"])
    assert result.exit_code == 0
    for flag in ("--name", "--peripheral", "--tx", "--rx", "--baud", "--apply"):
        assert flag in result.output


# ---------------------------------------------------------------------------
# diff-only / --apply
# ---------------------------------------------------------------------------


def test_alloy_add_uart_diff_only_does_not_modify_files(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    before = (tmp_path / PROJECT_FILE).read_text()
    result = CliRunner().invoke(
        cli, ["add", "uart", "--name", "app", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "+++" in result.output  # unified diff header
    assert (tmp_path / PROJECT_FILE).read_text() == before
    assert not (tmp_path / "src" / "peripherals.cpp").exists()


def test_alloy_add_uart_apply_writes_alloy_toml_and_cpp(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    result = CliRunner().invoke(
        cli,
        ["add", "uart", "--name", "app", "--apply", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    config = read(tmp_path / PROJECT_FILE)
    assert any(p.kind == "uart" and p.name == "app" for p in config.peripherals)
    cpp = (tmp_path / "src" / "peripherals.cpp").read_text()
    assert "alloy::Uart app" in cpp
    assert "AUTO-GENERATED" in cpp


def test_alloy_add_uart_invalid_pin_fails_without_modifying_files(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            "add",
            "uart",
            "--name",
            "app",
            "--peripheral",
            "USART1",
            "--tx",
            "PA12",
            "--rx",
            "PA13",
            "--apply",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "PA12" in result.output
    config = read(tmp_path / PROJECT_FILE)
    assert config.peripherals == ()


def test_alloy_add_uart_conflict_fails(tmp_path, patched_ir) -> None:
    # Pre-populate USART2 → PA2/PA3.
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(
            __import__("alloy_cli.core.project", fromlist=["PeripheralEntry"]).PeripheralEntry(
                kind="uart",
                name="debug",
                payload={
                    "kind": "uart",
                    "name": "debug",
                    "peripheral": "USART2",
                    "tx": "PA2",
                    "rx": "PA3",
                },
            ),
        ),
        build={},
        flash={},
        raw={},
    )
    write(tmp_path / PROJECT_FILE, config)
    result = CliRunner().invoke(
        cli,
        [
            "add",
            "uart",
            "--name",
            "app",
            "--peripheral",
            "USART2",
            "--tx",
            "PA2",
            "--rx",
            "PA3",
            "--apply",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    output = result.output.lower()
    assert "in-use" in output or "in use" in output or "wired up" in output


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


def test_alloy_add_gpio_apply_then_diff_only_shows_no_changes(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    apply = CliRunner().invoke(
        cli,
        ["add", "gpio", "--name", "led", "--pin", "PA5", "--apply", "--project-dir", str(tmp_path)],
    )
    assert apply.exit_code == 0, apply.output
    cpp_first = (tmp_path / "src" / "peripherals.cpp").read_text()

    diff = CliRunner().invoke(
        cli,
        ["add", "gpio", "--name", "led2", "--pin", "PA5", "--project-dir", str(tmp_path)],
    )
    # Same pin → conflict diagnostic, exit non-zero, no files written.
    assert diff.exit_code != 0
    cpp_second = (tmp_path / "src" / "peripherals.cpp").read_text()
    assert cpp_first == cpp_second


def test_emit_is_byte_stable_across_apply_runs(tmp_path, patched_ir) -> None:
    _seed_project(tmp_path)
    CliRunner().invoke(
        cli,
        ["add", "gpio", "--name", "led", "--pin", "PA5", "--apply", "--project-dir", str(tmp_path)],
    )
    text_first = (tmp_path / "src" / "peripherals.cpp").read_bytes()

    # Re-run apply with the same name+pin → caught as a duplicate-name
    # conflict; the file is unchanged.
    CliRunner().invoke(
        cli,
        ["add", "gpio", "--name", "led", "--pin", "PA5", "--apply", "--project-dir", str(tmp_path)],
    )
    text_second = (tmp_path / "src" / "peripherals.cpp").read_bytes()
    assert text_first == text_second
