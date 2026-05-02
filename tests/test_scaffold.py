"""Tests for ``alloy_cli.core.scaffold`` — the engine behind ``alloy new``."""

from __future__ import annotations

import json

import pytest

from alloy_cli.core import boards
from alloy_cli.core.errors import BoardNotFoundError, DeviceNotFoundError
from alloy_cli.core.project import PROJECT_FILE, read
from alloy_cli.core.scaffold import (
    SUPPORTED_LICENSES,
    ScaffoldError,
    ScaffoldRequest,
    scaffold,
    validate_project_name,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def board_catalog(tmp_path, monkeypatch):
    """Drop a ``nucleo_g071rb`` board.json + a ``rpi_pico`` board.json
    under ``tmp_path`` and point ALLOY_BOARDS_ROOT at it."""
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
                "uart": {
                    "debug": {
                        "peripheral": "USART2",
                        "tx": "PA2",
                        "rx": "PA3",
                        "baud": 115200,
                    }
                },
                "leds": [{"name": "ld4", "pin": "PA5"}],
                "clock_profiles": ["default_pll_64mhz"],
                "tier": 1,
            }
        )
    )

    pico = catalog / "rpi_pico"
    pico.mkdir()
    (pico / "board.json").write_text(
        json.dumps(
            {
                "board_id": "rpi_pico",
                "vendor": "rp",
                "family": "rp2040",
                "device": "rp2040",
                "arch": "cortex-m0plus",
                "mcu": "RP2040",
                "flash_size_bytes": 2097152,
                "summary": "Raspberry Pi Pico",
                "leds": [{"name": "led", "pin": "GPIO25"}],
                "clock_profiles": ["default_125mhz"],
                "tier": 1,
            }
        )
    )

    bare = catalog / "bare_chip_demo"
    bare.mkdir()
    (bare / "board.json").write_text(
        json.dumps(
            {
                "board_id": "bare_chip_demo",
                "vendor": "st",
                "family": "stm32f4",
                "device": "stm32f407vg",
                "arch": "cortex-m4",
                "mcu": "STM32F407VG",
                "flash_size_bytes": 1048576,
                "summary": "Bare F407 demo",
                "tier": 2,
            }
        )
    )

    monkeypatch.setenv("ALLOY_BOARDS_ROOT", str(catalog))
    boards.load_catalog.cache_clear()
    yield catalog
    boards.load_catalog.cache_clear()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_project_name_accepts_valid_names() -> None:
    for name in ("blinky", "Blinky", "my-firmware", "my_firmware", "Demo123"):
        validate_project_name(name)


def test_validate_project_name_rejects_invalid() -> None:
    for name in ("1blinky", "-prefix", "_underscore", "with space", ""):
        with pytest.raises(ScaffoldError, match="Project name"):
            validate_project_name(name)


def test_scaffold_rejects_when_neither_board_nor_device(tmp_path) -> None:
    req = ScaffoldRequest(
        name="firmware", destination=tmp_path / "firmware", board_id=None, device=None
    )
    with pytest.raises(ScaffoldError, match="exactly one"):
        scaffold(req)


def test_scaffold_rejects_when_both_board_and_device(tmp_path) -> None:
    req = ScaffoldRequest(
        name="firmware",
        destination=tmp_path / "firmware",
        board_id="nucleo_g071rb",
        device=("st", "stm32g0", "stm32g071rb"),
    )
    with pytest.raises(ScaffoldError, match="exactly one"):
        scaffold(req)


def test_scaffold_rejects_unknown_license(tmp_path, board_catalog) -> None:
    req = ScaffoldRequest(
        name="firmware",
        destination=tmp_path / "firmware",
        board_id="nucleo_g071rb",
        license="GPL-99",
    )
    with pytest.raises(ScaffoldError, match="Unsupported license"):
        scaffold(req)


def test_scaffold_rejects_non_empty_destination(tmp_path, board_catalog) -> None:
    dest = tmp_path / "firmware"
    dest.mkdir()
    (dest / "stale").write_text("hi")
    req = ScaffoldRequest(
        name="firmware",
        destination=dest,
        board_id="nucleo_g071rb",
    )
    with pytest.raises(ScaffoldError, match="not empty"):
        scaffold(req)


def test_scaffold_force_allows_non_empty_destination(tmp_path, board_catalog) -> None:
    dest = tmp_path / "firmware"
    dest.mkdir()
    (dest / "stale").write_text("hi")
    req = ScaffoldRequest(
        name="firmware",
        destination=dest,
        board_id="nucleo_g071rb",
        force=True,
        init_git=False,
    )
    result = scaffold(req)
    assert (result.destination / PROJECT_FILE).exists()


# ---------------------------------------------------------------------------
# Happy-path: --board
# ---------------------------------------------------------------------------


def _scaffold_board(tmp_path, board_id: str = "nucleo_g071rb"):
    req = ScaffoldRequest(
        name="firmware",
        destination=tmp_path / "firmware",
        board_id=board_id,
        init_git=False,
    )
    return scaffold(req)


def test_scaffold_with_board_writes_alloy_toml_validating_against_schema(
    tmp_path, board_catalog
) -> None:
    result = _scaffold_board(tmp_path)
    config = read(result.destination / PROJECT_FILE)
    assert config.board is not None
    assert config.board.id == "nucleo_g071rb"
    assert config.chip is None


def test_scaffold_with_board_populates_debug_uart_and_led(tmp_path, board_catalog) -> None:
    result = _scaffold_board(tmp_path)
    kinds = [p.kind for p in result.config.peripherals]
    assert "uart" in kinds
    assert "gpio" in kinds
    uart = next(p for p in result.config.peripherals if p.kind == "uart")
    assert uart.payload["peripheral"] == "USART2"
    assert uart.payload["tx"] == "PA2"
    assert uart.payload["rx"] == "PA3"
    assert uart.payload["baud"] == 115200
    led = next(p for p in result.config.peripherals if p.kind == "gpio")
    assert led.payload["pin"] == "PA5"
    assert led.payload["mode"] == "output"


def test_scaffold_with_board_picks_first_clock_profile(tmp_path, board_catalog) -> None:
    result = _scaffold_board(tmp_path)
    assert result.config.clocks == {"profile": "default_pll_64mhz"}


def test_scaffold_writes_expected_file_set(tmp_path, board_catalog) -> None:
    result = _scaffold_board(tmp_path)
    relpaths = sorted(p.relative_to(result.destination).as_posix() for p in result.files_written)
    assert relpaths == [
        ".gitignore",
        "CMakeLists.txt",
        "LICENSE",
        "README.md",
        "alloy.toml",
        "src/main.cpp",
    ]


def test_scaffold_cmakelists_calls_alloy_cli_init(tmp_path, board_catalog) -> None:
    result = _scaffold_board(tmp_path)
    text = (result.destination / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "alloy_cli_init()" in text
    assert "alloy_cli_link(${ALLOY_PROJECT_NAME})" in text
    assert "find_package(Python3 REQUIRED COMPONENTS Interpreter)" in text


def test_scaffold_main_cpp_uses_board_init_when_led_present(tmp_path, board_catalog) -> None:
    result = _scaffold_board(tmp_path)
    main = (result.destination / "src" / "main.cpp").read_text(encoding="utf-8")
    assert "alloy::board::init()" in main
    assert "alloy::board::led::toggle()" in main


def test_scaffold_readme_mentions_target_and_license(tmp_path, board_catalog) -> None:
    req = ScaffoldRequest(
        name="firmware",
        destination=tmp_path / "firmware",
        board_id="nucleo_g071rb",
        license="Apache-2.0",
        init_git=False,
    )
    result = scaffold(req)
    readme = (result.destination / "README.md").read_text(encoding="utf-8")
    assert "firmware" in readme
    assert "ST Nucleo-G071RB" in readme
    assert "Apache-2.0" in readme


def test_scaffold_license_file_uses_chosen_license(tmp_path, board_catalog) -> None:
    req = ScaffoldRequest(
        name="firmware",
        destination=tmp_path / "firmware",
        board_id="nucleo_g071rb",
        license="MIT",
        author="Jane Roe",
        init_git=False,
    )
    result = scaffold(req)
    license_text = (result.destination / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Jane Roe" in license_text


def test_scaffold_supported_licenses_contains_all_three() -> None:
    assert set(SUPPORTED_LICENSES) == {"MIT", "Apache-2.0", "BSD-3"}


# ---------------------------------------------------------------------------
# Board variants
# ---------------------------------------------------------------------------


def test_scaffold_board_without_uart_skips_console_peripheral(tmp_path, board_catalog) -> None:
    result = _scaffold_board(tmp_path, board_id="rpi_pico")
    kinds = [p.kind for p in result.config.peripherals]
    assert "uart" not in kinds
    assert "gpio" in kinds  # rp pico still has an LED


def test_scaffold_bare_board_yields_empty_peripherals(tmp_path, board_catalog) -> None:
    result = _scaffold_board(tmp_path, board_id="bare_chip_demo")
    assert result.config.peripherals == ()
    main = (result.destination / "src" / "main.cpp").read_text(encoding="utf-8")
    # No LED ⇒ falls back to the idle stub.
    assert "alloy::board::init()" not in main
    assert "while (true)" in main


def test_scaffold_unknown_board_raises(tmp_path, board_catalog) -> None:
    req = ScaffoldRequest(
        name="firmware",
        destination=tmp_path / "firmware",
        board_id="not-real",
        init_git=False,
    )
    # ScaffoldError wraps the underlying BoardNotFoundError so the CLI
    # can present the message verbatim.
    with pytest.raises((ScaffoldError, BoardNotFoundError)):
        scaffold(req)


# ---------------------------------------------------------------------------
# Happy-path: --device
# ---------------------------------------------------------------------------


def test_scaffold_with_device_raises_pending_chip_only_followup(
    tmp_path, board_catalog
) -> None:
    """Chip-only scaffolds are deliberately rejected after #wire-alloy-hal-fetchcontent.

    The CMakeLists template flows ALLOY_BOARD down to alloy/'s
    CMake to pick the linker / startup, so today only board-driven
    projects can produce a buildable tree.  A follow-up
    `wire-chip-only-projects` proposal will resolve the
    chip → board metadata directly.
    """
    from alloy_cli.core import ir

    registry = ir.discovered_device_registry()
    if not registry:
        pytest.skip("alloy-devices-yml submodule not initialised")
    (vendor, family), devices = next(iter(registry.items()))
    device = devices[0]

    req = ScaffoldRequest(
        name="raw",
        destination=tmp_path / "raw",
        device=(vendor, family, device),
        init_git=False,
    )
    with pytest.raises(ScaffoldError) as exc:
        scaffold(req)
    assert "chip-only" in str(exc.value).lower()
    assert "wire-chip-only-projects" in str(exc.value)


def test_scaffold_unknown_device_raises(tmp_path, board_catalog) -> None:
    """Both unknown-device + chip-only paths raise ScaffoldError today.

    The chip-only refusal fires before the registry lookup, so any
    device triple now flows through the same error.  Until the
    chip-only follow-up lands this is the correct contract.
    """
    req = ScaffoldRequest(
        name="raw",
        destination=tmp_path / "raw",
        device=("acme", "fictional", "ax-001"),
        init_git=False,
    )
    with pytest.raises((ScaffoldError, DeviceNotFoundError)):
        scaffold(req)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_scaffold_alloy_toml_is_deterministic(tmp_path, board_catalog) -> None:
    a = scaffold(
        ScaffoldRequest(
            name="firmware",
            destination=tmp_path / "a",
            board_id="nucleo_g071rb",
            init_git=False,
        )
    )
    b = scaffold(
        ScaffoldRequest(
            name="firmware",
            destination=tmp_path / "b",
            board_id="nucleo_g071rb",
            init_git=False,
        )
    )
    assert (a.destination / PROJECT_FILE).read_bytes() == (
        b.destination / PROJECT_FILE
    ).read_bytes()
