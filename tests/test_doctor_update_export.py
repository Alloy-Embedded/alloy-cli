"""Tests for `alloy doctor` / `alloy update` / `alloy export` + advanced TUI views."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core import export as _export
from alloy_cli.core import update as _update
from alloy_cli.core.lockfile import AlloyLockfile, write_lock
from alloy_cli.core.project import (
    PROJECT_FILE,
    AlloyDir,
    BoardRef,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.main import cli
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.dma_matrix import DmaMatrixScreen
from alloy_cli.tui.screens.memory_map import MemoryMapScreen
from alloy_cli.tui.widgets.dma_matrix import DmaMatrix, DmaMatrixCell, DmaMatrixWidget
from alloy_cli.tui.widgets.memory_map import (
    MemoryMap,
    MemoryMapWidget,
    Section,
    parse_size_lines,
)


def _seed_project(root: Path) -> ProjectConfig:
    config = ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(
            name="firmware",
            alloy="0.7.5",
            alloy_codegen="0.4.2",
            alloy_devices_yml="1.5.1",
            alloy_cli="0.5.0",
        ),
        board=BoardRef(id="nucleo_g071rb"),
        chip=None,
        clocks={},
        peripherals=(),
        build={"profile": "release"},
        flash={},
        raw={},
    )
    write(root / PROJECT_FILE, config)
    return config


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


def test_diagnose_run_returns_report_with_checks(tmp_path) -> None:
    _seed_project(tmp_path)
    report = _diagnose.run(project_dir=tmp_path)
    names = [c.name for c in report.checks]
    assert "cmake" in names
    assert "alloy.toml" in names


def test_diagnose_to_dict_emits_schema_version(tmp_path) -> None:
    _seed_project(tmp_path)
    report = _diagnose.run(project_dir=tmp_path)
    payload = report.to_dict()
    assert payload["schema_version"] == "1.1"
    assert isinstance(payload["checks"], list)


def test_alloy_doctor_help() -> None:
    result = CliRunner().invoke(cli, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output


def test_alloy_doctor_json_emits_decoded_payload(tmp_path) -> None:
    _seed_project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--json", "--project-dir", str(tmp_path)])
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1.1"


def test_alloy_doctor_exits_nonzero_when_check_fails(tmp_path, monkeypatch) -> None:
    _seed_project(tmp_path)

    class _MissingStatus:
        present = False
        path = None
        version = None
        install_hint = "brew install thing"

    from alloy_cli.core import toolchain

    monkeypatch.setattr(toolchain, "detect_arm_gcc", lambda: _MissingStatus())
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_resolve_upgrades_lists_change(tmp_path) -> None:
    config = _seed_project(tmp_path)
    lock = AlloyLockfile(
        schema_version="1.0.0",
        alloy="0.7.3",
        alloy_codegen="0.4.1",
        alloy_devices_yml="1.5.0",
        alloy_cli="0.5.0",
    )
    upgrades = _update.resolve_upgrades(config, lock)
    by_component = {u.component: u for u in upgrades}
    assert by_component["alloy"].current == "0.7.3"
    assert by_component["alloy"].target == "0.7.5"
    assert by_component["alloy"].is_change()
    assert not by_component["alloy-cli"].is_change()


def test_apply_upgrades_writes_new_lockfile(tmp_path, monkeypatch) -> None:
    """apply_upgrades returns an UpgradeReport whose .new_lock is the rewrite."""
    config = _seed_project(tmp_path)
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    write_lock(
        layout.lockfile,
        AlloyLockfile(
            schema_version="1.0.0",
            alloy="0.7.3",
            alloy_codegen="0.4.1",
            alloy_devices_yml="1.5.0",
            alloy_cli="0.5.0",
        ),
    )
    upgrades = _update.resolve_upgrades(
        config,
        AlloyLockfile(
            schema_version="1.0.0",
            alloy="0.7.3",
            alloy_codegen="0.4.1",
            alloy_devices_yml="1.5.0",
            alloy_cli="0.5.0",
        ),
    )

    # Stub every upgrader to a no-op success — focus the test on the
    # lockfile-rewrite contract.
    def _ok(_upgrade, _ctx):
        return _update.UpgradeOutcome(ok=True, log="ok")

    monkeypatch.setattr(
        _update,
        "UPGRADERS",
        {name: _ok for name in _update.DEPENDENCY_ORDER},
    )
    report = _update.apply_upgrades(tmp_path, upgrades=upgrades, config=config)
    assert report.aborted is False
    assert report.new_lock is not None
    assert report.new_lock.alloy == "0.7.5"


def test_alloy_update_dry_run_does_not_modify_lockfile(tmp_path) -> None:
    _seed_project(tmp_path)
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    write_lock(
        layout.lockfile,
        AlloyLockfile(
            schema_version="1.0.0",
            alloy="0.7.3",
            alloy_codegen="0.4.1",
            alloy_devices_yml="1.5.0",
            alloy_cli="0.5.0",
        ),
    )
    before = layout.lockfile.read_bytes()
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--dry-run", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "0.7.3" in result.output
    assert "0.7.5" in result.output
    assert layout.lockfile.read_bytes() == before


def test_alloy_update_frozen_refuses_change(tmp_path) -> None:
    _seed_project(tmp_path)
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    write_lock(
        layout.lockfile,
        AlloyLockfile(
            schema_version="1.0.0",
            alloy="0.7.3",
            alloy_codegen=None,
            alloy_devices_yml=None,
            alloy_cli=None,
        ),
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["update", "--frozen", "--project-dir", str(tmp_path)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_vscode_returns_three_files() -> None:
    config = _make_chip_config()
    files = _export.emit("vscode", config)
    rels = sorted(p.as_posix() for p in files)
    assert rels == [".vscode/c_cpp_properties.json", ".vscode/launch.json", ".vscode/tasks.json"]


def test_export_ci_github_default_target() -> None:
    config = _make_chip_config()
    files = _export.emit("ci", config)
    assert Path(".github/workflows/firmware.yml") in files


def test_export_ci_unknown_target_raises() -> None:
    config = _make_chip_config()
    with pytest.raises(ValueError):
        _export.emit("ci", config, target="travis")


def test_export_bom_includes_chip_and_peripherals() -> None:
    config = _make_chip_config()
    files = _export.emit("bom", config)
    bom = json.loads(next(iter(files.values())))
    assert bom["chip"]["device"] == "stm32g071rb"


def test_alloy_export_vscode_writes_files(tmp_path) -> None:
    _seed_project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["export", "vscode", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".vscode" / "launch.json").exists()
    assert (tmp_path / ".vscode" / "tasks.json").exists()
    launch = json.loads((tmp_path / ".vscode" / "launch.json").read_text())
    assert launch["configurations"][0]["type"] == "cortex-debug"
    tasks = json.loads((tmp_path / ".vscode" / "tasks.json").read_text())
    labels = {t["label"] for t in tasks["tasks"]}
    assert {"alloy build", "alloy flash", "alloy debug"} <= labels


def _make_chip_config() -> ProjectConfig:
    return ProjectConfig(
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


# ---------------------------------------------------------------------------
# TUI advanced views
# ---------------------------------------------------------------------------


def test_dma_matrix_from_pairs_orders_rows_and_columns() -> None:
    matrix = DmaMatrix.from_pairs(
        [
            DmaMatrixCell(peripheral_signal="USART1_TX", channel="DMA1_CH1", state="bound"),
            DmaMatrixCell(peripheral_signal="USART1_RX", channel="DMA1_CH2", state="bound"),
            DmaMatrixCell(peripheral_signal="USART1_TX", channel="DMA1_CH2", state="conflict"),
        ]
    )
    assert matrix.rows == ["USART1_TX", "USART1_RX"]
    assert matrix.columns == ["DMA1_CH1", "DMA1_CH2"]
    assert matrix.cells[("USART1_TX", "DMA1_CH1")].state == "bound"


def test_parse_size_lines_returns_sections() -> None:
    sections = parse_size_lines(
        [
            "   text\tdata\tbss\tdec\thex\tfilename",
            "  10240    512   4096   14848   3a00 firmware.elf",
        ]
    )
    by_name = {s.name: s for s in sections}
    assert by_name[".text"].size_bytes == 10240
    assert by_name[".bss"].region == "ram"


@pytest.mark.asyncio
async def test_dma_matrix_screen_renders_bound_cells() -> None:
    matrix = DmaMatrix.from_pairs(
        [
            DmaMatrixCell(peripheral_signal="USART1_TX", channel="DMA1_CH1", state="bound"),
            DmaMatrixCell(peripheral_signal="USART1_RX", channel="DMA1_CH2", state="bound"),
        ]
    )
    app = TuiApp(initial_screen=DmaMatrixScreen(matrix=matrix))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        widget = app.screen.query_one(DmaMatrixWidget)
        rows = "\n".join(str(s.render()) for s in widget.query("Static"))
        assert "USART1_TX" in rows
        assert "USART1_RX" in rows
        assert "●" in rows


@pytest.mark.asyncio
async def test_memory_map_screen_renders_flash_percentage() -> None:
    memory = MemoryMap(
        flash_capacity=131072,
        ram_capacity=36864,
        sections=(
            Section(name=".text", region="flash", size_bytes=32768),
            Section(name=".rodata", region="flash", size_bytes=0),
            Section(name=".data", region="flash", size_bytes=0),
            Section(name=".bss", region="ram", size_bytes=8192),
        ),
    )
    app = TuiApp(initial_screen=MemoryMapScreen(memory=memory))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        widget = app.screen.query_one(MemoryMapWidget)
        text = "\n".join(str(s.render()) for s in widget.query("Static"))
        assert "FLASH" in text
        assert "RAM" in text
        assert "25%" in text
