"""Tests for the ``alloy.list_family_toolchain`` MCP tool.

Covers the spec scenarios in
``openspec/changes/add-toolchain-registry/specs/mcp-surface/spec.md``:

  * Known family returns the resolved manifest with required + recommended
    + optional arrays + per-tool source / capabilities / install_docs.
  * Vendor-source recommended tools (e.g. STM32CubeProgrammer on stm32f4)
    carry per-OS install_docs URLs.
  * Unknown family returns a typed error envelope with `known_families`.
  * The tool appears in the registry's discoverable name set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alloy_cli.core.process import FakeRunner
from alloy_cli.mcp import ToolError, ToolRegistry, build_default_registry


@pytest.fixture
def registry(tmp_path: Path) -> ToolRegistry:
    """A fresh registry rooted at a temp project dir.

    Most family-toolchain tests don't actually need a project on
    disk (the tool is project-independent), but using tmp_path
    keeps the registry hermetic.
    """
    return build_default_registry(project_dir=tmp_path, runner=FakeRunner())


# ---------------------------------------------------------------------------
# Discoverability
# ---------------------------------------------------------------------------


def test_tool_is_listed_in_registry(registry: ToolRegistry) -> None:
    assert "list_family_toolchain" in registry.names()
    tool = registry.get_tool("list_family_toolchain")
    assert tool.description, "tool must carry a non-empty docstring"
    # Parameter schema declares family_id: string
    assert dict(tool.parameter_schema) == {"family_id": "string"}


# ---------------------------------------------------------------------------
# Known families
# ---------------------------------------------------------------------------


def test_returns_full_manifest_for_known_family(registry: ToolRegistry) -> None:
    payload = registry.call("list_family_toolchain", family_id="stm32g0")
    assert isinstance(payload, dict)
    assert payload["family_id"] == "stm32g0"
    assert payload["core"] == "cortex-m0plus"
    assert payload["schema_version"] == "1.0.0"
    assert payload["extends"] == "arm-cortex-m"
    assert payload["chain"] == ["arm-cortex-m"]

    required = payload["required"]
    assert isinstance(required, list)
    required_names = [entry["tool"] for entry in required]
    # Inherited from arm-cortex-m base
    for tool in ("arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"):
        assert tool in required_names, f"{tool} missing from required"


def test_required_entries_carry_full_tool_shape(registry: ToolRegistry) -> None:
    payload = registry.call("list_family_toolchain", family_id="stm32g0")
    arm_gcc = next(e for e in payload["required"] if e["tool"] == "arm-none-eabi-gcc")
    # Every documented field is present, even when empty
    assert set(arm_gcc.keys()) == {
        "tool",
        "version",
        "source",
        "capabilities",
        "bundles",
        "udev_required",
        "install_docs",
    }
    assert arm_gcc["source"] == "xpack"
    assert "build" in arm_gcc["capabilities"]
    assert "debug" in arm_gcc["capabilities"]
    # Bundled binaries flatten into the entry's bundles list
    assert "arm-none-eabi-gdb" in arm_gcc["bundles"]


def test_probe_rs_entry_carries_udev_required(registry: ToolRegistry) -> None:
    """Linux users need this hint surfaced — confirm it round-trips."""
    payload = registry.call("list_family_toolchain", family_id="stm32g0")
    probe_rs = next(e for e in payload["required"] if e["tool"] == "probe-rs")
    assert probe_rs["udev_required"] is True
    assert probe_rs["source"] == "probe-rs-installer"


def test_recommended_vendor_tool_has_per_os_install_docs(
    registry: ToolRegistry,
) -> None:
    payload = registry.call("list_family_toolchain", family_id="stm32f4")
    cube = next(
        e for e in payload["recommended"] if e["tool"] == "STM32CubeProgrammer"
    )
    assert cube["source"] == "vendor"
    docs = cube["install_docs"]
    # All three OS keys present + look like URLs
    for os_key in ("linux", "macos", "windows"):
        assert os_key in docs
        assert docs[os_key].startswith("https://")
    # And it's an st.com URL
    assert "st.com" in docs["macos"].lower()


def test_esp32_returns_espressif_tools_no_arm_gcc(registry: ToolRegistry) -> None:
    payload = registry.call("list_family_toolchain", family_id="esp32")
    assert payload["family_id"] == "esp32"
    assert payload["extends"] is None
    assert payload["chain"] == []

    required_names = {entry["tool"] for entry in payload["required"]}
    assert "xtensa-esp-elf-gcc" in required_names
    assert "esptool" in required_names
    # Cortex-M tooling is gone
    assert "arm-none-eabi-gcc" not in required_names
    assert "probe-rs" not in required_names

    xtensa = next(
        e for e in payload["required"] if e["tool"] == "xtensa-esp-elf-gcc"
    )
    assert xtensa["source"] == "espressif"


def test_arm_cortex_m_base_loads_directly(registry: ToolRegistry) -> None:
    """The shared base is itself a callable family id — useful for
    contributors authoring child manifests.
    """
    payload = registry.call("list_family_toolchain", family_id="arm-cortex-m")
    assert payload["family_id"] == "arm-cortex-m"
    assert payload["extends"] is None
    assert payload["chain"] == []
    required_names = {entry["tool"] for entry in payload["required"]}
    assert {"arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"} <= required_names


# ---------------------------------------------------------------------------
# Unknown families
# ---------------------------------------------------------------------------


def test_unknown_family_raises_typed_error_with_known_list(
    registry: ToolRegistry,
) -> None:
    with pytest.raises(ToolError) as exc_info:
        registry.call("list_family_toolchain", family_id="totally-not-a-family")
    err = exc_info.value
    assert err.error_type == "family-toolchain-not-found"
    assert "totally-not-a-family" in err.message

    # The envelope (via to_dict) carries known_families for the LLM.
    envelope = err.to_dict()
    assert envelope["error_type"] == "family-toolchain-not-found"
    assert "known_families" in envelope
    known = envelope["known_families"]
    assert isinstance(known, list)
    for fid in ("arm-cortex-m", "esp32", "nrf52", "rp2040", "stm32f4", "stm32g0"):
        assert fid in known


def test_unknown_family_envelope_includes_message(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError) as exc_info:
        registry.call("list_family_toolchain", family_id="ghost-family")
    envelope = exc_info.value.to_dict()
    assert envelope["message"]
    assert "ghost-family" in envelope["message"]


# ---------------------------------------------------------------------------
# JSON-friendliness
# ---------------------------------------------------------------------------


def test_response_is_json_serialisable(registry: ToolRegistry) -> None:
    """Every value in the response must round-trip through json.dumps —
    the stdio MCP transport serialises responses verbatim, and a
    non-JSON value would crash the server mid-call.
    """
    import json as _json

    payload = registry.call("list_family_toolchain", family_id="rp2040")
    blob = _json.dumps(payload, sort_keys=True)
    # Round-trip is identical
    assert _json.loads(blob) == payload


def test_response_uses_lists_not_tuples(registry: ToolRegistry) -> None:
    """Tuples don't survive JSON serialisation as tuples — guarantee
    the projection converts every tuple to a list before emit.
    """
    payload = registry.call("list_family_toolchain", family_id="stm32g0")
    assert isinstance(payload["required"], list)
    assert isinstance(payload["chain"], list)
    arm_gcc = next(e for e in payload["required"] if e["tool"] == "arm-none-eabi-gcc")
    assert isinstance(arm_gcc["capabilities"], list)
    assert isinstance(arm_gcc["bundles"], list)
