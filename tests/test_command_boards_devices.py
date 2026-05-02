"""Smoke tests for ``alloy boards`` and ``alloy devices`` Click commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from alloy_cli.core import boards as _boards
from alloy_cli.core import search as _search
from alloy_cli.main import cli


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    root = tmp_path / "boards"
    root.mkdir()
    nucleo = root / "nucleo_g071rb"
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
                "tier": 1,
                "clock_profiles": ["pll_64mhz"],
            }
        )
    )
    f4 = root / "stm32f4_disco"
    f4.mkdir()
    (f4 / "board.json").write_text(
        json.dumps(
            {
                "board_id": "stm32f4_disco",
                "vendor": "st",
                "family": "stm32f4",
                "device": "stm32f407vg",
                "arch": "cortex-m4",
                "mcu": "STM32F407VGT6",
                "flash_size_bytes": 1048576,
                "summary": "STM32F4 Discovery",
                "tier": 1,
                "clock_profiles": ["pll_168mhz"],
                "usb": {"otg": "fs"},
            }
        )
    )
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(root))
    _boards.load_catalog.cache_clear()
    _search.reset_caches()
    yield root
    _boards.load_catalog.cache_clear()
    _search.reset_caches()


# ---------------------------------------------------------------------------
# alloy boards
# ---------------------------------------------------------------------------


def test_alloy_boards_help_lists_options() -> None:
    result = CliRunner().invoke(cli, ["boards", "--help"])
    assert result.exit_code == 0
    assert "--search" in result.output
    assert "--vendor" in result.output
    assert "--isa" in result.output
    assert "--has" in result.output
    assert "--tier" in result.output
    assert "--json" in result.output


def test_alloy_boards_lists_catalogue(catalogue) -> None:
    """JSON mode is the contract surface; the rendered table is cosmetic."""
    result = CliRunner().invoke(cli, ["boards", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    ids = {b["board_id"] for b in payload["boards"]}
    assert ids == {"nucleo_g071rb", "stm32f4_disco"}


def test_alloy_boards_search_filters_results(catalogue) -> None:
    result = CliRunner().invoke(cli, ["boards", "--search", "nucleo", "--json"])
    assert result.exit_code == 0
    ids = {b["board_id"] for b in json.loads(result.output)["boards"]}
    assert ids == {"nucleo_g071rb"}


def test_alloy_boards_isa_filter(catalogue) -> None:
    result = CliRunner().invoke(cli, ["boards", "--isa", "cortex-m4", "--json"])
    assert result.exit_code == 0
    ids = {b["board_id"] for b in json.loads(result.output)["boards"]}
    assert ids == {"stm32f4_disco"}


def test_alloy_boards_json_emits_stable_schema(catalogue) -> None:
    result = CliRunner().invoke(cli, ["boards", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1.0"
    assert isinstance(payload["boards"], list)
    sample = payload["boards"][0]
    for key in (
        "board_id",
        "mcu",
        "vendor",
        "family",
        "core",
        "flash_size_bytes",
        "clock_profiles",
        "tier",
    ):
        assert key in sample


def test_alloy_boards_detail_card(catalogue) -> None:
    result = CliRunner().invoke(cli, ["boards", "nucleo_g071rb"])
    assert result.exit_code == 0
    assert "nucleo_g071rb" in result.output
    assert "stm32g0" in result.output
    assert "cortex-m0plus" in result.output


def test_alloy_boards_detail_unknown_returns_error(catalogue) -> None:
    result = CliRunner().invoke(cli, ["boards", "unknown_board"])
    assert result.exit_code != 0
    assert "unknown_board" in result.output


def test_alloy_boards_no_results_hint(catalogue) -> None:
    result = CliRunner().invoke(cli, ["boards", "--search", "zzz_nope"])
    assert result.exit_code == 0
    assert "no matching" in result.output.lower()


# ---------------------------------------------------------------------------
# alloy devices
# ---------------------------------------------------------------------------


def test_alloy_devices_help_lists_options() -> None:
    result = CliRunner().invoke(cli, ["devices", "--help"])
    assert result.exit_code == 0
    assert "--search" in result.output
    assert "--vendor" in result.output
    assert "--family" in result.output
    assert "--admitted" in result.output
    assert "--all" in result.output
    assert "--json" in result.output


def test_alloy_devices_default_lists_admitted(catalogue) -> None:
    result = CliRunner().invoke(cli, ["devices"])
    if "no matching" in result.output.lower():
        pytest.skip("alloy-devices-yml submodule not initialised")
    assert result.exit_code == 0
    assert "device" in result.output.lower()


def test_alloy_devices_json_schema(catalogue) -> None:
    result = CliRunner().invoke(cli, ["devices", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1.0"
    assert isinstance(payload["devices"], list)


def test_alloy_devices_all_flag_includes_bulk(catalogue) -> None:
    result_admitted = CliRunner().invoke(cli, ["devices", "--json"])
    result_all = CliRunner().invoke(cli, ["devices", "--all", "--json"])
    if result_admitted.exit_code != 0 or result_all.exit_code != 0:
        pytest.skip("submodule not initialised")
    admitted_count = len(json.loads(result_admitted.output)["devices"])
    all_count = len(json.loads(result_all.output)["devices"])
    if admitted_count == 0 and all_count == 0:
        pytest.skip("alloy-devices-yml submodule empty")
    assert all_count >= admitted_count
