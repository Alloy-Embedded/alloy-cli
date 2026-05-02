"""Tests for ``add-export-ci-toolchain-matrix`` (#28)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from alloy_cli.core import export as _export
from alloy_cli.core.export import _core_from_device_name, _toolchain_step, github_workflow
from alloy_cli.core.project import (
    PROJECT_FILE,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.main import cli


def _config(*, vendor: str = "st", family: str = "stm32g0", device: str = "stm32g071rb") -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.1.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor=vendor, family=family, device=device),
        clocks={},
        peripherals=(),
        build={"profile": "release"},
        flash={},
        raw={},
    )


# ---------------------------------------------------------------------------
# _core_from_device_name + _toolchain_step
# ---------------------------------------------------------------------------


def test_core_from_device_name_picks_arm_for_stm32() -> None:
    assert _core_from_device_name("stm32g071rb") == "cortex-m"


def test_core_from_device_name_picks_riscv_for_esp32_c() -> None:
    assert _core_from_device_name("esp32-c3") == "riscv"


def test_core_from_device_name_picks_xtensa_for_esp32() -> None:
    assert _core_from_device_name("esp32") == "xtensa"


def test_core_from_device_name_handles_explicit_riscv_marker() -> None:
    assert _core_from_device_name("ch32v305rb") == "riscv"


def test_toolchain_step_arm_picks_carlosperate_action() -> None:
    snippet = _toolchain_step("cortex-m0plus")
    assert "carlosperate/arm-none-eabi-gcc-action" in snippet


def test_toolchain_step_riscv_uses_apt_get() -> None:
    snippet = _toolchain_step("rv32imac")
    assert "gcc-riscv64-unknown-elf" in snippet


def test_toolchain_step_xtensa_uses_espressif_action() -> None:
    snippet = _toolchain_step("xtensa-lx6")
    assert "espressif/install-esp-idf-action" in snippet


# ---------------------------------------------------------------------------
# github_workflow output
# ---------------------------------------------------------------------------


def test_github_workflow_yaml_is_well_formed() -> None:
    body = github_workflow(_config())
    payload = yaml.safe_load(body)
    assert payload["name"] == "firmware"
    assert "build" in payload["jobs"]
    matrix = payload["jobs"]["build"]["strategy"]["matrix"]
    assert sorted(matrix["profile"]) == ["debug", "release"]


def test_github_workflow_for_stm32_installs_arm_gcc() -> None:
    body = github_workflow(_config())
    assert "carlosperate/arm-none-eabi-gcc-action" in body


def test_github_workflow_for_esp32c3_installs_riscv() -> None:
    body = github_workflow(
        _config(vendor="espressif", family="esp32", device="esp32-c3")
    )
    assert "gcc-riscv64-unknown-elf" in body
    assert "carlosperate/arm-none-eabi-gcc-action" not in body


def test_github_workflow_includes_doctor_failure_step() -> None:
    body = github_workflow(_config())
    assert "alloy doctor --json" in body
    assert "if: failure()" in body


def test_github_workflow_uploads_artifacts() -> None:
    body = github_workflow(_config())
    assert "actions/upload-artifact" in body
    assert ".alloy/build/*.elf" in body


def test_github_workflow_caches_alloy_state() -> None:
    body = github_workflow(_config())
    assert "actions/cache" in body
    assert "alloy.toml" in body  # cache key references the manifest


def test_github_workflow_lands_at_firmware_yml(tmp_path: Path) -> None:
    config = _config()
    write(tmp_path / PROJECT_FILE, config)
    files = _export.emit("ci", config, target="github")
    assert Path(".github/workflows/firmware.yml") in files


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _seed(tmp_path: Path) -> None:
    write(tmp_path / PROJECT_FILE, _config())


def test_alloy_export_ci_writes_workflow(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["export", "ci", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    target = tmp_path / ".github" / "workflows" / "firmware.yml"
    assert target.exists()
    body = target.read_text(encoding="utf-8")
    assert "carlosperate/arm-none-eabi-gcc-action" in body


def test_alloy_export_ci_dry_run_prints_to_stdout(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export", "ci", "--project-dir", str(tmp_path), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "carlosperate/arm-none-eabi-gcc-action" in result.output
    assert not (tmp_path / ".github" / "workflows" / "firmware.yml").exists()


def test_alloy_export_help_advertises_dry_run() -> None:
    result = CliRunner().invoke(cli, ["export", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


@pytest.mark.parametrize(
    "device,marker",
    [
        ("stm32g071rb", "carlosperate/arm-none-eabi-gcc-action"),
        ("esp32-c6", "gcc-riscv64-unknown-elf"),
        ("esp32-s3", "espressif/install-esp-idf-action"),
    ],
)
def test_workflow_toolchain_matrix(device: str, marker: str) -> None:
    config = _config(device=device)
    body = github_workflow(config)
    assert marker in body
