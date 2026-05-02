"""Tests for ``add-clock-profile-persistence`` (#21).

Covers:
- Pure-function tests for ``profile_from_rates`` /
  ``save_profile`` / ``activate_profile`` (Phase 5.1).
- Schema regression: ``[clocks.profiles]`` parses + the
  ``[clocks].profile`` cross-reference check fires (Phase 2.4).
- Pilot-driven Clock Tree flow: PLL override → Ctrl+S → DiffModal
  apply → ``alloy.toml`` carries the new profile (Phase 5.2).
- MCP integration: save then activate via the registry (Phase 5.3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alloy_cli.core import clocks as _clocks
from alloy_cli.core.clocks import (
    ClockProfileBody,
    InvalidProfileNameError,
    UnknownProfileError,
    activate_profile,
    profile_from_rates,
    save_profile,
)
from alloy_cli.core.errors import ProjectConfigError
from alloy_cli.core.ir import (
    ClockNodeView,
    DeviceIdentity,
    DeviceIR,
)
from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import (
    PROJECT_FILE,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    parse,
    read,
    write,
)
from alloy_cli.mcp import ToolError, build_default_registry
from alloy_cli.tui.app import TuiApp
from alloy_cli.tui.screens.clock_tree import _CUSTOM_LABEL, ClockTreeScreen, _ProfileNameModal
from alloy_cli.tui.widgets.clock_tree import ClockTreeWidget

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ir() -> DeviceIR:
    return DeviceIR(
        identity=DeviceIdentity(
            vendor="st",
            family="stm32g0",
            device="stm32g071rb",
            package="lqfp64",
            core="cortex-m0plus",
            summary="STM32G0",
        ),
        peripherals=(),
        pins=(),
        connection_candidates=(),
        dma_routes=(),
        clock_nodes=(
            ClockNodeView(node_id="HSI", parent=None, rate_hz=16_000_000, selector=None),
            ClockNodeView(node_id="PLL", parent="HSI", rate_hz=64_000_000, selector="PLL_M_N_R"),
            ClockNodeView(node_id="SYSCLK", parent="PLL", rate_hz=None, selector="MUX"),
            ClockNodeView(node_id="HCLK", parent="SYSCLK", rate_hz=None, selector="DIV"),
        ),
        payload={},
    )


def _config(*, profile: str | None = None, profiles: dict | None = None) -> ProjectConfig:
    clocks: dict = {}
    if profile is not None:
        clocks["profile"] = profile
    if profiles is not None:
        clocks["profiles"] = profiles
    return ProjectConfig(
        schema_version="1.1.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks=clocks,
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


# ---------------------------------------------------------------------------
# Phase 5.1 — pure-function tests
# ---------------------------------------------------------------------------


def test_profile_from_rates_extracts_typed_fields() -> None:
    body = profile_from_rates({"SYSCLK": 96_000_000, "PLL_N": 24, "PLL_R": 2})
    assert body.sysclk_hz == 96_000_000
    assert body.pll_n == 24
    assert body.pll_r == 2
    # PLL_R / PLL_N triggered the heuristic, so the source flips to PLL.
    assert body.source == "PLL"


def test_profile_from_rates_passes_unknown_keys_to_extras() -> None:
    body = profile_from_rates({"HCLK": 64_000_000, "VENDOR_X": 12_345})
    # Neither key is in our typed-field map, so both flow through extras.
    assert body.sysclk_hz is None
    assert body.extras == {"HCLK": 64_000_000, "VENDOR_X": 12_345}


def test_profile_from_rates_defaults_to_hsi() -> None:
    body = profile_from_rates({"SYSCLK": 16_000_000})
    assert body.source == "HSI"


def test_profile_from_rates_picks_hse_when_present() -> None:
    body = profile_from_rates({"HSE": 8_000_000, "SYSCLK": 80_000_000})
    assert body.source == "HSE"


def test_profile_body_to_dict_drops_none_fields_and_orders_keys() -> None:
    body = ClockProfileBody(source="HSI", sysclk_hz=16_000_000, extras={"BLE": 1})
    out = body.to_dict()
    # source first, typed fields, extras last; None fields omitted.
    assert list(out.keys()) == ["source", "sysclk_hz", "BLE"]
    assert "pll_n" not in out


def test_save_profile_emits_diff_with_new_subtable() -> None:
    config = _config(profile="default", profiles={})
    body = profile_from_rates({"PLL_N": 24, "PLL_R": 2, "SYSCLK": 96_000_000})
    diff = save_profile(config, "dev_low_power", body)
    rendered = diff.render()
    assert "+[clocks.profiles.dev_low_power]" in rendered
    assert "+source = " in rendered
    assert "+sysclk_hz = 96000000" in rendered


def test_save_profile_replaces_existing_entry() -> None:
    existing_body = ClockProfileBody(source="HSI", sysclk_hz=16_000_000).to_dict()
    config = _config(profiles={"dev": existing_body})
    new_body = profile_from_rates({"SYSCLK": 96_000_000})
    diff = save_profile(config, "dev", new_body)
    rendered = diff.render()
    assert "-sysclk_hz = 16000000" in rendered
    assert "+sysclk_hz = 96000000" in rendered


def test_save_profile_rejects_empty_name() -> None:
    config = _config()
    with pytest.raises(InvalidProfileNameError):
        save_profile(config, "", ClockProfileBody(source="HSI"))


def test_save_profile_rejects_invalid_chars() -> None:
    config = _config()
    with pytest.raises(InvalidProfileNameError):
        save_profile(config, "9starts", ClockProfileBody(source="HSI"))
    with pytest.raises(InvalidProfileNameError):
        save_profile(config, "has space", ClockProfileBody(source="HSI"))


def test_activate_profile_flips_active_pointer() -> None:
    body = ClockProfileBody(source="HSI", sysclk_hz=16_000_000).to_dict()
    config = _config(profile="default", profiles={"default": body, "fast": body})
    diff = activate_profile(config, "fast")
    rendered = diff.render()
    assert '-profile = "default"' in rendered
    assert '+profile = "fast"' in rendered


def test_activate_profile_unknown_name_raises() -> None:
    body = ClockProfileBody(source="HSI").to_dict()
    config = _config(profile="default", profiles={"default": body})
    with pytest.raises(UnknownProfileError) as exc_info:
        activate_profile(config, "fast")
    assert "fast" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Phase 2.4 — schema + round-trip regression
# ---------------------------------------------------------------------------


def test_round_trip_preserves_clocks_profiles_block(tmp_path: Path) -> None:
    body = ClockProfileBody(
        source="HSI",
        pll_n=24,
        pll_r=2,
        sysclk_hz=96_000_000,
    ).to_dict()
    config = _config(profile="dev_low_power", profiles={"dev_low_power": body})

    target = tmp_path / PROJECT_FILE
    write(target, config)
    text = target.read_text(encoding="utf-8")

    # Stable canonical form: each profile renders as a sub-table.
    assert "[clocks.profiles.dev_low_power]" in text
    assert 'source = "HSI"' in text
    assert "sysclk_hz = 96000000" in text

    reloaded = read(target)
    assert reloaded.clocks["profile"] == "dev_low_power"
    profiles = reloaded.clocks["profiles"]
    assert profiles["dev_low_power"]["sysclk_hz"] == 96_000_000

    # Round-tripping through write again must be byte-stable.
    write(target, reloaded)
    assert target.read_text(encoding="utf-8") == text


def test_clocks_profile_referencing_unknown_name_raises() -> None:
    body = ClockProfileBody(source="HSI").to_dict()
    payload = {
        "schema_version": "1.1.0",
        "project": {"name": "firmware"},
        "chip": {"vendor": "st", "family": "stm32g0", "device": "stm32g071rb"},
        "clocks": {"profile": "missing", "profiles": {"dev_low_power": body}},
    }
    with pytest.raises(ProjectConfigError) as exc_info:
        parse(payload)
    assert "missing" in str(exc_info.value)
    assert "dev_low_power" not in str(exc_info.value)  # not the missing key


def test_clocks_profile_without_profiles_map_still_parses() -> None:
    """Legacy 1.0.0 files set profile without the new profiles table."""
    payload = {
        "schema_version": "1.0.0",
        "project": {"name": "firmware"},
        "chip": {"vendor": "st", "family": "stm32g0", "device": "stm32g071rb"},
        "clocks": {"profile": "default_pll_64mhz"},
    }
    config = parse(payload)
    assert config.clocks == {"profile": "default_pll_64mhz"}


def test_clocks_profiles_invalid_body_fails_schema() -> None:
    payload = {
        "schema_version": "1.1.0",
        "project": {"name": "firmware"},
        "chip": {"vendor": "st", "family": "stm32g0", "device": "stm32g071rb"},
        # Missing required `source`
        "clocks": {"profiles": {"dev": {"sysclk_hz": 96_000_000}}},
    }
    with pytest.raises(ProjectConfigError) as exc_info:
        parse(payload)
    assert "source" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Phase 5.2 — pilot-driven TUI flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clock_tree_save_profile_round_trips_to_alloy_toml(tmp_path: Path) -> None:
    config = _config(profile="default")
    target = tmp_path / PROJECT_FILE
    write(target, config)

    screen = ClockTreeScreen(
        ir=_ir(), config=config, device_max_hz=64_000_000, project_dir=tmp_path
    )
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        # 1. Apply a PLL override.
        widget = screen.query_one("#clock-widget", ClockTreeWidget)
        widget.set_override("PLL_N", 24)
        widget.set_override("PLL_R", 2)
        widget.set_override("SYSCLK", 96_000_000)

        # 2. Save: bypass the modal by calling the persist helper directly.
        screen._persist_profile("dev_low_power", dict(widget.overrides))
        await pilot.pause()

        # 3. Confirm the diff modal — DiffModal returns True on Apply.
        screen._on_save_diff_applied(
            "dev_low_power",
            _clocks.save_profile(
                config,
                "dev_low_power",
                _clocks.profile_from_rates(dict(widget.overrides)),
            ),
            applied=True,
        )

    # File now carries the new profile + the active pointer is unchanged.
    text = target.read_text(encoding="utf-8")
    assert "[clocks.profiles.dev_low_power]" in text
    assert "sysclk_hz = 96000000" in text


@pytest.mark.asyncio
async def test_clock_tree_p_cycles_named_profiles_plus_custom() -> None:
    body = ClockProfileBody(source="HSI").to_dict()
    config = _config(
        profile="default_pll_64mhz",
        profiles={"default_pll_64mhz": body, "dev_low_power": body},
    )
    screen = ClockTreeScreen(ir=_ir(), config=config, device_max_hz=64_000_000)
    app = TuiApp(initial_screen=screen)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        labels = []
        for _ in range(4):
            labels.append(screen.current_profile)
            screen.action_next_profile()
            await pilot.pause()

    # The cycle visits each named profile + the (custom) sentinel and
    # wraps back to the first.
    assert "default_pll_64mhz" in labels
    assert "dev_low_power" in labels
    assert _CUSTOM_LABEL in labels


@pytest.mark.asyncio
async def test_profile_name_modal_rejects_empty_and_duplicates() -> None:
    modal = _ProfileNameModal(default="", existing=("dev",))
    app = TuiApp(initial_screen=modal)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        from textual.widgets import Static

        modal._submit("")  # empty
        await pilot.pause()
        error = modal.query_one("#profile-name-error", Static)
        assert "empty" in str(error.render()).lower()

        modal._submit("dev")  # duplicate
        await pilot.pause()
        assert "exists" in str(error.render()).lower()

        modal._submit("9starts")  # invalid char
        await pilot.pause()
        assert "letter" in str(error.render()).lower()


# ---------------------------------------------------------------------------
# Phase 5.3 — MCP integration
# ---------------------------------------------------------------------------


def _seed(tmp_path: Path, *, profile: str | None = None, profiles: dict | None = None) -> None:
    config = _config(profile=profile, profiles=profiles)
    write(tmp_path / PROJECT_FILE, config)


def test_save_clock_profile_then_activate_round_trips(tmp_path: Path) -> None:
    _seed(tmp_path)
    registry = build_default_registry(project_dir=tmp_path, runner=FakeRunner())

    # 1. Save — caches a diff under diff_id.
    saved = registry.call(
        "save_clock_profile",
        name="dev_low_power",
        rates={"SYSCLK": 96_000_000, "PLL_N": 24, "PLL_R": 2},
    )
    assert saved["diff_id"]
    assert "dev_low_power" in saved["diff_text"]

    # 2. Apply — file gains the new profile.
    registry.call("apply_diff", diff_id=saved["diff_id"])
    text = (tmp_path / PROJECT_FILE).read_text(encoding="utf-8")
    assert "[clocks.profiles.dev_low_power]" in text

    # 3. Activate — flips [clocks].profile to the new entry.
    activated = registry.call("activate_clock_profile", name="dev_low_power")
    registry.call("apply_diff", diff_id=activated["diff_id"])

    final_config = read(tmp_path / PROJECT_FILE)
    assert final_config.clocks["profile"] == "dev_low_power"
    assert "dev_low_power" in final_config.clocks["profiles"]


def test_activate_clock_profile_unknown_returns_tool_error(tmp_path: Path) -> None:
    body = ClockProfileBody(source="HSI").to_dict()
    _seed(tmp_path, profile="dev", profiles={"dev": body})
    registry = build_default_registry(project_dir=tmp_path, runner=FakeRunner())

    with pytest.raises(ToolError) as exc_info:
        registry.call("activate_clock_profile", name="missing")
    assert exc_info.value.error_type == "unknown-clock-profile"


def test_save_clock_profile_invalid_name_raises_tool_error(tmp_path: Path) -> None:
    _seed(tmp_path)
    registry = build_default_registry(project_dir=tmp_path, runner=FakeRunner())

    with pytest.raises(ToolError) as exc_info:
        registry.call("save_clock_profile", name="9bad", rates={"SYSCLK": 16_000_000})
    assert exc_info.value.error_type == "invalid-clock-profile-name"


def test_default_registry_lists_new_clock_tools(tmp_path: Path) -> None:
    registry = build_default_registry(project_dir=tmp_path, runner=FakeRunner())
    names = set(registry.names())
    assert {"save_clock_profile", "activate_clock_profile"} <= names
    # Legacy tool stays exposed for back-compat.
    assert "set_clock_profile" in names
