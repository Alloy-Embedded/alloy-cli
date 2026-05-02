"""Tests for ``alloy_cli.core.search`` — boards + devices faceted search."""

from __future__ import annotations

import json

import pytest

from alloy_cli.core import boards as _boards
from alloy_cli.core import search as _search
from alloy_cli.core.search import BoardFilters, DeviceFilters


@pytest.fixture
def board_catalog(tmp_path, monkeypatch):
    """Catalogue with two boards: one Cortex-M0+, one Cortex-M4 with USB."""
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
                "summary": "ST Nucleo G071RB",
                "tier": 1,
                "clock_profiles": ["pll_64mhz"],
            }
        )
    )

    disco = catalog / "stm32f4_disco"
    disco.mkdir()
    (disco / "board.json").write_text(
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
    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(catalog))
    _boards.load_catalog.cache_clear()
    yield catalog
    _boards.load_catalog.cache_clear()


# ---------------------------------------------------------------------------
# search_boards
# ---------------------------------------------------------------------------


def test_search_boards_no_filters_returns_full_catalogue(board_catalog) -> None:
    results = _search.search_boards()
    assert len(results) == 2
    assert {b.board_id for b in results} == {"nucleo_g071rb", "stm32f4_disco"}


def test_search_boards_query_matches_substring(board_catalog) -> None:
    results = _search.search_boards(query="nucleo")
    assert len(results) == 1
    assert results[0].board_id == "nucleo_g071rb"


def test_search_boards_query_matches_mcu(board_catalog) -> None:
    results = _search.search_boards(query="stm32g071")
    assert any(b.board_id == "nucleo_g071rb" for b in results)


def test_search_boards_filter_by_vendor(board_catalog) -> None:
    results = _search.search_boards(filters=BoardFilters(vendor="st"))
    assert len(results) == 2


def test_search_boards_filter_by_isa(board_catalog) -> None:
    results = _search.search_boards(filters=BoardFilters(isa="cortex-m4"))
    assert {b.board_id for b in results} == {"stm32f4_disco"}


def test_search_boards_filter_by_feature(board_catalog) -> None:
    results = _search.search_boards(filters=BoardFilters(has=("usb",)))
    assert {b.board_id for b in results} == {"stm32f4_disco"}


def test_search_boards_filter_by_tier(board_catalog) -> None:
    results = _search.search_boards(filters=BoardFilters(tier=1))
    assert len(results) == 2
    results_t99 = _search.search_boards(filters=BoardFilters(tier=99))
    assert results_t99 == ()


def test_search_boards_combines_query_and_filter(board_catalog) -> None:
    results = _search.search_boards(query="disco", filters=BoardFilters(isa="cortex-m4"))
    assert len(results) == 1
    assert results[0].board_id == "stm32f4_disco"


def test_search_boards_empty_when_no_match(board_catalog) -> None:
    assert _search.search_boards(query="zzz_no_match") == ()


# ---------------------------------------------------------------------------
# search_devices
# ---------------------------------------------------------------------------


def test_search_devices_returns_admitted_devices() -> None:
    _search.reset_caches()
    results = _search.search_devices(filters=DeviceFilters(admitted="admitted"))
    if not results:
        pytest.skip("alloy-devices-yml submodule not initialised")
    assert all(d.admitted for d in results)


def test_search_devices_query_matches_device_id() -> None:
    _search.reset_caches()
    # Pick a device that exists in the registry, search for its full id
    registry = __import__("alloy_cli.core.ir", fromlist=["discovered_device_registry"])
    devices = registry.discovered_device_registry()
    if not devices:
        pytest.skip("alloy-devices-yml submodule not initialised")
    (vendor, family), names = next(iter(devices.items()))
    needle = names[0]
    results = _search.search_devices(query=needle)
    assert any(d.vendor == vendor and d.family == family and d.device == needle for d in results)


def test_search_devices_filter_by_vendor() -> None:
    _search.reset_caches()
    results = _search.search_devices(filters=DeviceFilters(vendor="st"))
    if not results:
        pytest.skip("no ST admitted devices in submodule")
    assert all(d.vendor == "st" for d in results)


def test_search_devices_admitted_all_includes_bulk() -> None:
    _search.reset_caches()
    admitted = _search.search_devices(filters=DeviceFilters(admitted="admitted"))
    every = _search.search_devices(filters=DeviceFilters(admitted="all"))
    if not every:
        pytest.skip("alloy-devices-yml submodule not initialised")
    # `all` must be at least as large as admitted, and contain ≥1 non-admitted entry.
    assert len(every) >= len(admitted)
    assert any(not d.admitted for d in every)


def test_search_devices_summaries_have_identity_fields() -> None:
    _search.reset_caches()
    results = _search.search_devices()
    if not results:
        pytest.skip("alloy-devices-yml submodule not initialised")
    sample = results[0]
    assert sample.vendor
    assert sample.family
    assert sample.device


# ---------------------------------------------------------------------------
# boards_referencing_device
# ---------------------------------------------------------------------------


def test_boards_referencing_device_returns_match(board_catalog) -> None:
    matches = _search.boards_referencing_device("st", "stm32g0", "stm32g071rb")
    assert len(matches) == 1
    assert matches[0].board_id == "nucleo_g071rb"


def test_boards_referencing_device_empty_when_no_match(board_catalog) -> None:
    assert _search.boards_referencing_device("acme", "fake", "ax-001") == ()
