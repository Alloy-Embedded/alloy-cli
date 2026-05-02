"""Smoke tests for ``core.boards``."""

from __future__ import annotations

import json

import pytest

from alloy_cli.core import boards
from alloy_cli.core.errors import BoardNotFoundError


@pytest.fixture
def fixture_boards_root(tmp_path, monkeypatch):
    """Build a tiny board catalogue under ``tmp_path`` and point
    ``ALLOY_BOARDS_ROOT`` at it."""
    nucleo = tmp_path / "nucleo_g071rb"
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
                "uart": {"debug": {"peripheral": "USART2", "tx": "PA2", "rx": "PA3"}},
                "leds": [{"name": "ld4", "pin": "PA5"}],
                "clock_profiles": ["default_pll_64mhz"],
                "tier": 1,
            }
        )
    )
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(tmp_path))
    boards.load_catalog.cache_clear()
    yield tmp_path
    boards.load_catalog.cache_clear()


def test_load_catalog_reads_board_json(fixture_boards_root) -> None:
    catalog = boards.load_catalog()
    assert len(catalog) == 1
    summary = catalog[0]
    assert summary.board_id == "nucleo_g071rb"
    assert summary.vendor == "st"
    assert summary.tier == 1
    assert "led" in summary.has_features
    assert "debug-uart" in summary.has_features


def test_lookup_returns_full_manifest(fixture_boards_root) -> None:
    manifest = boards.lookup("nucleo_g071rb")
    assert manifest.mcu == "STM32G071RBT6"
    assert manifest.payload["uart"]["debug"]["peripheral"] == "USART2"


def test_lookup_unknown_raises(fixture_boards_root) -> None:
    with pytest.raises(BoardNotFoundError):
        boards.lookup("not-a-board")


def test_empty_catalog_when_root_unset(monkeypatch) -> None:
    monkeypatch.delenv("ALLOY_BOARDS_ROOT", raising=False)
    boards.load_catalog.cache_clear()
    assert boards.load_catalog() == ()
    boards.load_catalog.cache_clear()
