"""Smoke tests for the ``alloy new`` Click command surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import boards
from alloy_cli.main import cli


@pytest.fixture
def board_catalog(tmp_path, monkeypatch):
    catalog = tmp_path / "boards"
    catalog.mkdir()
    nucleo = catalog / "nucleo_g071rb"
    nucleo.mkdir()
    (nucleo / "board.json").write_text(
        json.dumps(
            {
                "board_id": "nucleo_g071rb",
                "vendor": "st",
                "family": "stm32g0",
                "device": "stm32g071rb",
                "arch": "cortex-m0plus",
                "mcu": "STM32G071RBT6",
                "flash_size_bytes": 131072,
                "summary": "ST Nucleo-G071RB",
                "uart": {"debug": {"peripheral": "USART2", "tx": "PA2", "rx": "PA3"}},
                "leds": [{"name": "ld4", "pin": "PA5"}],
                "clock_profiles": ["default_pll_64mhz"],
                "tier": 1,
            }
        )
    )
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(catalog))
    boards.load_catalog.cache_clear()
    yield catalog
    boards.load_catalog.cache_clear()


def test_alloy_new_help_lists_options() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["new", "--help"])
    assert result.exit_code == 0
    assert "--board" in result.output
    assert "--device" in result.output
    assert "--license" in result.output
    assert "--git" in result.output
    assert "--force" in result.output


def test_alloy_new_without_board_or_device_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["new", "firmware"])
    assert result.exit_code != 0
    assert "alloy boards" in result.output or "--board" in result.output


def test_alloy_new_with_both_board_and_device_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            [
                "new",
                "firmware",
                "--board",
                "nucleo_g071rb",
                "--device",
                "st/stm32g0/stm32g071rb",
            ],
        )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_alloy_new_with_invalid_device_format_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "firmware", "--device", "stm32g071rb"],
        )
    assert result.exit_code != 0
    assert "VENDOR/FAMILY/DEVICE" in result.output


def test_alloy_new_board_writes_a_buildable_project_tree(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(
            cli,
            ["new", "firmware", "--board", "nucleo_g071rb", "--no-git"],
        )
        assert result.exit_code == 0, result.output
        project = Path(cwd) / "firmware"
        assert (project / "alloy.toml").exists()
        assert (project / "CMakeLists.txt").exists()
        assert (project / "src" / "main.cpp").exists()
        assert (project / "README.md").exists()
        assert (project / ".gitignore").exists()
        assert (project / "LICENSE").exists()


def test_alloy_new_unknown_board_surfaces_clean_error(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "firmware", "--board", "fictional_board", "--no-git"],
        )
    assert result.exit_code != 0
    assert "fictional_board" in result.output


def test_alloy_new_invalid_project_name_fails(tmp_path, board_catalog) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(
            cli,
            ["new", "1bad-name", "--board", "nucleo_g071rb", "--no-git"],
        )
    assert result.exit_code != 0
    assert "Project name" in result.output
