"""Smoke tests for the ``alloy build`` / ``flash`` / ``debug`` Click surfaces."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import process as _process
from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import (
    PROJECT_FILE,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
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


@pytest.fixture
def fake_process(monkeypatch):
    """Swap the module-level :data:`process.runner` with a fresh FakeRunner.

    Also stubs out toolchain detection so build/flash/debug skip the
    "is arm-gcc on PATH?" check.
    """
    fake = FakeRunner()
    restore = _process.configure(fake)

    from alloy_cli.core import toolchain

    class _Status:
        present = True
        path = "/stub"
        version = "stub"
        install_hint = None

    for name in (
        "detect_arm_gcc",
        "detect_cmake",
        "detect_ninja",
        "detect_probe_rs",
        "detect_openocd",
    ):
        monkeypatch.setattr(toolchain, name, lambda: _Status())  # type: ignore[arg-type]

    # Pretend `size` isn't on PATH so the build CLI doesn't try to call
    # arm-none-eabi-size after the build (which the FakeRunner has no
    # expectation for).
    monkeypatch.setattr("alloy_cli.core.memory.shutil.which", lambda _name: None)

    yield fake
    restore()


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def test_alloy_build_help_lists_options() -> None:
    result = CliRunner().invoke(cli, ["build", "--help"])
    assert result.exit_code == 0
    assert "--profile" in result.output
    assert "--clean" in result.output


def test_alloy_build_invokes_cmake_and_ninja(tmp_path, fake_process) -> None:
    _seed_project(tmp_path)
    fake_process.expect(["cmake", "-S"], returncode=0)
    fake_process.expect(["cmake", "--build"], returncode=0)
    # Pre-create an ELF so the resolver finds something.
    build_dir = tmp_path / ".alloy" / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "firmware.elf").write_bytes(b"\x7fELF")

    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Build OK" in result.output


def test_alloy_build_reports_cmake_failure(tmp_path, fake_process) -> None:
    _seed_project(tmp_path)
    fake_process.expect(["cmake", "-S"], returncode=2, stdout="oops")

    result = CliRunner().invoke(cli, ["build", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "Build failed" in result.output


# ---------------------------------------------------------------------------
# flash
# ---------------------------------------------------------------------------


def test_alloy_flash_help_lists_options() -> None:
    result = CliRunner().invoke(cli, ["flash", "--help"])
    assert result.exit_code == 0
    assert "--probe" in result.output
    assert "--target" in result.output
    assert "--elf" in result.output


def test_alloy_flash_runs_against_single_probe(tmp_path, fake_process) -> None:
    _seed_project(tmp_path)
    elf = tmp_path / ".alloy" / "build" / "firmware.elf"
    elf.parent.mkdir(parents=True, exist_ok=True)
    elf.write_bytes(b"\x7fELF")

    fake_process.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps([{"type": "stlink", "serial_number": "abc"}]),
        returncode=0,
    )
    fake_process.expect(["probe-rs", "run"], returncode=0, stdout="OK")

    result = CliRunner().invoke(cli, ["flash", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Flashed" in result.output


def test_alloy_flash_errors_when_no_probes(tmp_path, fake_process) -> None:
    _seed_project(tmp_path)
    elf = tmp_path / ".alloy" / "build" / "firmware.elf"
    elf.parent.mkdir(parents=True, exist_ok=True)
    elf.write_bytes(b"\x7fELF")

    fake_process.expect(["probe-rs", "list", "--output=json"], stdout="[]", returncode=0)
    fake_process.expect(["probe-rs", "list"], stdout="", returncode=0)

    result = CliRunner().invoke(cli, ["flash", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "no debug probe" in result.output.lower()


def test_alloy_flash_errors_when_multiple_probes_and_no_choice(tmp_path, fake_process) -> None:
    _seed_project(tmp_path)
    elf = tmp_path / ".alloy" / "build" / "firmware.elf"
    elf.parent.mkdir(parents=True, exist_ok=True)
    elf.write_bytes(b"\x7fELF")

    fake_process.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps(
            [
                {"type": "stlink", "serial_number": "a"},
                {"type": "jlink", "serial_number": "b"},
            ]
        ),
        returncode=0,
    )

    result = CliRunner().invoke(cli, ["flash", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "2 probes" in result.output or "--probe" in result.output


def test_alloy_flash_errors_when_no_elf(tmp_path, fake_process) -> None:
    _seed_project(tmp_path)
    result = CliRunner().invoke(cli, ["flash", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "No ELF" in result.output


# ---------------------------------------------------------------------------
# debug
# ---------------------------------------------------------------------------


def test_alloy_debug_help_lists_options() -> None:
    result = CliRunner().invoke(cli, ["debug", "--help"])
    assert result.exit_code == 0
    assert "--probe" in result.output
    assert "--gdb-ui" in result.output
    assert "--gdb-port" in result.output


def test_alloy_debug_dry_run_prints_invocations(tmp_path, fake_process, monkeypatch) -> None:
    _seed_project(tmp_path)
    elf = tmp_path / ".alloy" / "build" / "firmware.elf"
    elf.parent.mkdir(parents=True, exist_ok=True)
    elf.write_bytes(b"\x7fELF")

    fake_process.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps([{"type": "stlink", "serial_number": "abc"}]),
        returncode=0,
    )

    # Make _resolve_gdb find a binary deterministically.
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name)

    result = CliRunner().invoke(
        cli,
        ["debug", "--project-dir", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "gdb-server" in result.output
    assert "probe-rs" in result.output
    assert "gdb" in result.output
