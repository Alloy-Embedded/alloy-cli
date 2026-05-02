"""Tests for ``core.project``: read, write, validate, round-trip."""

from __future__ import annotations

import tomllib

import pytest

from alloy_cli.core.errors import ProjectConfigError, ProjectConfigVersionError
from alloy_cli.core.project import (
    PROJECT_FILE,
    SCHEMA_VERSION,
    AlloyDir,
    BoardRef,
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
    parse,
    read,
    write,
)

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _minimal_board_payload() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {"name": "demo"},
        "board": {"id": "stm32f4-discovery"},
    }


def _full_payload() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "name": "blinky",
            "alloy-cli": "0.5.0",
            "alloy": "0.7.3",
            "alloy-codegen": "0.4.1",
            "alloy-devices-yml": "1.5.0",
        },
        "chip": {"vendor": "st", "family": "stm32f4", "device": "stm32f407vg"},
        "clocks": {"profile": "max"},
        "peripherals": [
            {
                "kind": "gpio",
                "name": "led_green",
                "pin": "PD12",
                "mode": "output",
                "initial": 0,
            },
            {
                "kind": "uart",
                "name": "console",
                "peripheral": "USART2",
                "tx": "PA2",
                "rx": "PA3",
                "baud": 115200,
            },
        ],
        "build": {"profile": "release", "optimization": "size", "lto": True},
        "flash": {"probe": "stlink", "openocd_config": "openocd/stm32f4-discovery.cfg"},
    }


# ---------------------------------------------------------------------------
# parse() — happy paths
# ---------------------------------------------------------------------------


def test_parse_minimal_board_project() -> None:
    cfg = parse(_minimal_board_payload())
    assert cfg.schema_version == SCHEMA_VERSION
    assert cfg.project.name == "demo"
    assert cfg.board == BoardRef(id="stm32f4-discovery")
    assert cfg.chip is None
    assert cfg.peripherals == ()


def test_parse_full_chip_project() -> None:
    cfg = parse(_full_payload())
    assert cfg.project.name == "blinky"
    assert cfg.project.alloy_cli == "0.5.0"
    assert cfg.project.alloy_devices_yml == "1.5.0"
    assert cfg.chip == ChipRef(vendor="st", family="stm32f4", device="stm32f407vg")
    assert cfg.board is None
    assert cfg.clocks == {"profile": "max"}
    assert len(cfg.peripherals) == 2
    led, console = cfg.peripherals
    assert isinstance(led, PeripheralEntry)
    assert led.kind == "gpio"
    assert led.name == "led_green"
    assert led.payload["mode"] == "output"
    assert console.kind == "uart"
    assert console.payload["baud"] == 115200
    assert cfg.build == {"profile": "release", "optimization": "size", "lto": True}
    assert cfg.flash["probe"] == "stlink"


# ---------------------------------------------------------------------------
# parse() — schema_version handling
# ---------------------------------------------------------------------------


def test_parse_missing_schema_version_raises() -> None:
    payload = _minimal_board_payload()
    del payload["schema_version"]
    with pytest.raises(ProjectConfigError, match="schema_version"):
        parse(payload)


def test_parse_higher_major_version_raises_version_error() -> None:
    payload = _minimal_board_payload()
    payload["schema_version"] = "2.0.0"
    with pytest.raises(ProjectConfigVersionError, match="upgrade alloy-cli"):
        parse(payload)


def test_parse_malformed_version_raises_config_error() -> None:
    payload = _minimal_board_payload()
    payload["schema_version"] = "v1"
    with pytest.raises(ProjectConfigError, match="SemVer"):
        parse(payload)


def test_parse_higher_minor_within_major_one_succeeds() -> None:
    payload = _minimal_board_payload()
    payload["schema_version"] = "1.99.0"
    cfg = parse(payload)
    assert cfg.schema_version == "1.99.0"


# ---------------------------------------------------------------------------
# parse() — schema validation negatives
# ---------------------------------------------------------------------------


def test_parse_rejects_when_neither_board_nor_chip_present() -> None:
    payload = {"schema_version": SCHEMA_VERSION, "project": {"name": "demo"}}
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_invalid_project_name_pattern() -> None:
    payload = _minimal_board_payload()
    payload["project"]["name"] = "1starts-with-digit"
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_uart_peripheral_missing_tx() -> None:
    payload = _minimal_board_payload()
    payload["peripherals"] = [
        {
            "kind": "uart",
            "name": "console",
            "peripheral": "USART2",
            # tx missing
            "rx": "PA3",
        }
    ]
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_unknown_peripheral_kind() -> None:
    payload = _minimal_board_payload()
    payload["peripherals"] = [{"kind": "telepathy", "name": "x"}]
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_gpio_with_invalid_mode() -> None:
    payload = _minimal_board_payload()
    payload["peripherals"] = [{"kind": "gpio", "name": "led", "pin": "PA0", "mode": "magic"}]
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_unknown_top_level_key() -> None:
    payload = _minimal_board_payload()
    payload["mystery"] = {"foo": "bar"}
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_build_profile_not_in_enum() -> None:
    payload = _minimal_board_payload()
    payload["build"] = {"profile": "yolo"}
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_spi_missing_required_pins() -> None:
    payload = _minimal_board_payload()
    payload["peripherals"] = [{"kind": "spi", "name": "nor", "peripheral": "SPI1", "sck": "PA5"}]
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_i2c_with_invalid_speed() -> None:
    payload = _minimal_board_payload()
    payload["peripherals"] = [
        {
            "kind": "i2c",
            "name": "sensor",
            "peripheral": "I2C1",
            "sda": "PB7",
            "scl": "PB6",
            "speed": "ludicrous",
        }
    ]
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


def test_parse_rejects_chip_missing_device() -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project": {"name": "demo"},
        "chip": {"vendor": "st", "family": "stm32f4"},
    }
    with pytest.raises(ProjectConfigError, match="schema validation"):
        parse(payload)


# ---------------------------------------------------------------------------
# read() / write() round-trip
# ---------------------------------------------------------------------------


def test_read_missing_file_raises(tmp_path) -> None:
    with pytest.raises(ProjectConfigError, match="alloy new"):
        read(tmp_path / PROJECT_FILE)


def test_write_then_read_roundtrip_preserves_structure(tmp_path) -> None:
    payload = _full_payload()
    cfg = parse(payload)
    out = tmp_path / PROJECT_FILE
    write(out, cfg)

    text = out.read_text(encoding="utf-8")
    # Sanity-check deterministic output starts with schema_version
    assert text.startswith(f'schema_version = "{SCHEMA_VERSION}"\n'), text[:80]

    decoded = read(out)
    assert decoded.schema_version == cfg.schema_version
    assert decoded.project == cfg.project
    assert decoded.chip == cfg.chip
    assert decoded.board is None
    assert decoded.clocks == cfg.clocks
    # Peripheral payloads round-trip identically (kind/name + extras)
    assert len(decoded.peripherals) == len(cfg.peripherals)
    for original, reread in zip(cfg.peripherals, decoded.peripherals, strict=True):
        assert original.kind == reread.kind
        assert original.name == reread.name
        assert original.payload == reread.payload
    assert decoded.build == cfg.build
    assert decoded.flash == cfg.flash


def test_write_emits_board_section_when_board_present(tmp_path) -> None:
    cfg = parse(_minimal_board_payload())
    out = tmp_path / PROJECT_FILE
    write(out, cfg)
    text = out.read_text(encoding="utf-8")
    assert "[board]" in text
    assert 'id = "stm32f4-discovery"' in text
    assert "[chip]" not in text


def test_write_creates_parent_directories(tmp_path) -> None:
    cfg = parse(_minimal_board_payload())
    out = tmp_path / "nested" / "subdir" / PROJECT_FILE
    write(out, cfg)
    assert out.exists()


def test_write_is_deterministic_byte_for_byte(tmp_path) -> None:
    cfg = parse(_full_payload())
    a = tmp_path / "a.toml"
    b = tmp_path / "b.toml"
    write(a, cfg)
    write(b, cfg)
    assert a.read_bytes() == b.read_bytes()


def test_write_then_tomllib_parse_yields_same_payload(tmp_path) -> None:
    """The emitted TOML must be valid TOML and round-trip through tomllib."""
    cfg = parse(_full_payload())
    out = tmp_path / PROJECT_FILE
    write(out, cfg)
    with out.open("rb") as fp:
        decoded = tomllib.load(fp)
    assert decoded["schema_version"] == cfg.schema_version
    assert decoded["project"]["name"] == "blinky"
    assert decoded["chip"]["device"] == "stm32f407vg"
    assert len(decoded["peripherals"]) == 2
    assert decoded["peripherals"][0]["kind"] == "gpio"
    assert decoded["build"]["lto"] is True


# ---------------------------------------------------------------------------
# AlloyDir layout
# ---------------------------------------------------------------------------


def test_alloydir_paths_resolve_under_project_root(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    assert layout.base == tmp_path / ".alloy"
    assert layout.lockfile == tmp_path / ".alloy" / "version.lock"
    assert layout.cache == tmp_path / ".alloy" / "cache"
    assert layout.generated == tmp_path / ".alloy" / "generated"


def test_alloydir_ensure_creates_subdirs_idempotently(tmp_path) -> None:
    layout = AlloyDir(root=tmp_path)
    layout.ensure()
    layout.ensure()  # second call must not raise
    assert layout.cache.is_dir()
    assert layout.generated.is_dir()


# ---------------------------------------------------------------------------
# Construction sanity
# ---------------------------------------------------------------------------


def test_project_meta_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    meta = ProjectMeta(name="demo")
    with pytest.raises(FrozenInstanceError):
        meta.name = "other"  # type: ignore[misc]


def test_project_config_exposes_raw_payload() -> None:
    payload = _minimal_board_payload()
    cfg = parse(payload)
    assert cfg.raw is payload
    assert isinstance(cfg, ProjectConfig)
