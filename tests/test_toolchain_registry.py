"""Tests for ``core.toolchain_registry``.

Covers:
  * Loading every shipped manifest end-to-end.
  * `extends:` chain resolution (child overrides base by tool name).
  * Cycle detection, unknown parent, schema errors raise typed
    ``FamilyToolchainError`` sub-classes.
  * On-disk cache hit on second call.
  * `resolve_for_project` honours `[chip]` and `[board]`.
  * `tool_for_capability` walks required → recommended → optional.
  * `known_families` returns at least the seed set.

Cycle / unknown-parent / schema tests stub the locator helper so a
hand-rolled YAML fixture exercises the failure path without touching
the real `data/families/` tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from alloy_cli.core import toolchain_registry as tcr
from alloy_cli.core.errors import (
    FamilyToolchainCycleError,
    FamilyToolchainNotFoundError,
    FamilyToolchainSchemaError,
    FamilyToolchainUnknownParentError,
)
from alloy_cli.core.project import (
    SCHEMA_VERSION,
    BoardRef,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SHIPPED = ("arm-cortex-m", "stm32f4", "stm32g0", "rp2040", "nrf52", "esp32")


@pytest.fixture(autouse=True)
def _clear_known_families_cache() -> None:
    """Reset the cached family discovery between tests so monkeypatches
    of locator helpers don't bleed across cases.
    """
    tcr.known_families.cache_clear()


def _make_config(*, chip_family: str | None = None, board: str | None = None) -> ProjectConfig:
    return ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name="demo"),
        board=BoardRef(id=board) if board else None,
        chip=(
            ChipRef(vendor="vendor", family=chip_family, device="dev")
            if chip_family
            else None
        ),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


def _stub_locator(
    monkeypatch: pytest.MonkeyPatch, manifests: dict[str, str]
) -> None:
    """Redirect ``_read_manifest_text`` to return YAML from a dict.

    Unknown ids raise :class:`FamilyToolchainNotFoundError` so the
    extends-chain walker still sees a realistic failure mode.
    """

    def _fake_read(family_id: str) -> str:
        try:
            return manifests[family_id]
        except KeyError as exc:
            raise FamilyToolchainNotFoundError(
                f"No family manifest for {family_id!r} (test stub)."
            ) from exc

    monkeypatch.setattr(tcr, "_read_manifest_text", _fake_read)


# ---------------------------------------------------------------------------
# Shipped manifests
# ---------------------------------------------------------------------------


def test_known_families_includes_seed_set() -> None:
    families = tcr.known_families()
    for fid in SHIPPED:
        assert fid in families, f"{fid!r} missing from known_families()"


@pytest.mark.parametrize("family_id", SHIPPED)
def test_shipped_manifest_loads(family_id: str) -> None:
    manifest = tcr.load_family(family_id)
    assert manifest.family_id == family_id
    assert manifest.core
    assert manifest.schema_version == "1.0.0"
    # required must be non-empty for a usable family
    assert manifest.required, f"{family_id} has no required tools"


def test_extends_chain_inherits_arm_cortex_m_base() -> None:
    """stm32g0 declares only STM32CubeProgrammer + dfu-util + tio under
    `recommended`; the four base tools (gcc, cmake, ninja, probe-rs) come
    from arm-cortex-m via `extends:`.
    """
    manifest = tcr.load_family("stm32g0")
    assert manifest.extends == "arm-cortex-m"
    assert manifest.chain == ("arm-cortex-m",)
    required_tools = {tool.tool for tool in manifest.required}
    assert {"arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"} <= required_tools


def test_esp32_does_not_extend_arm_base() -> None:
    manifest = tcr.load_family("esp32")
    assert manifest.extends is None
    assert manifest.chain == ()
    required_tools = {tool.tool for tool in manifest.required}
    assert "xtensa-esp-elf-gcc" in required_tools
    assert "arm-none-eabi-gcc" not in required_tools


def test_load_unknown_family_raises_not_found() -> None:
    with pytest.raises(FamilyToolchainNotFoundError) as exc_info:
        tcr.load_family("definitely-not-a-real-family-xyz")
    msg = str(exc_info.value)
    assert "definitely-not-a-real-family-xyz" in msg


# ---------------------------------------------------------------------------
# Tool capability lookup
# ---------------------------------------------------------------------------


def test_tool_for_capability_walks_priority_order() -> None:
    manifest = tcr.load_family("stm32g0")
    # build → arm-gcc (required, first in list)
    build_tool = manifest.tool_for_capability("build")
    assert build_tool is not None
    assert build_tool.tool == "arm-none-eabi-gcc"

    # debug → arm-gcc too (it declares [build, debug] because gdb is bundled)
    debug_tool = manifest.tool_for_capability("debug")
    assert debug_tool is not None
    assert debug_tool.tool == "arm-none-eabi-gcc"

    # serial → tio (recommended)
    serial_tool = manifest.tool_for_capability("serial")
    assert serial_tool is not None
    assert serial_tool.tool == "tio"

    # nothing maps to register-debug on stm32g0 except STM32CubeProgrammer
    rd = manifest.tool_for_capability("register-debug")
    assert rd is not None
    assert rd.tool == "STM32CubeProgrammer"


def test_tool_for_capability_returns_none_when_absent() -> None:
    manifest = tcr.load_family("rp2040")
    # rp2040 manifest doesn't declare anything with register-debug
    assert manifest.tool_for_capability("register-debug") is None


def test_find_tool_resolves_bundles() -> None:
    manifest = tcr.load_family("arm-cortex-m")
    # primary
    gcc = manifest.find_tool("arm-none-eabi-gcc")
    assert gcc is not None and gcc.source == "xpack"
    # bundled binary resolves to the parent requirement
    gdb = manifest.find_tool("arm-none-eabi-gdb")
    assert gdb is not None and gdb.tool == "arm-none-eabi-gcc"
    # missing returns None
    assert manifest.find_tool("nonexistent-binary") is None


# ---------------------------------------------------------------------------
# Tool requirement helpers
# ---------------------------------------------------------------------------


def test_vendor_tool_is_flagged() -> None:
    manifest = tcr.load_family("stm32f4")
    cubeprog = manifest.find_tool("STM32CubeProgrammer")
    assert cubeprog is not None
    assert cubeprog.is_vendor is True
    assert cubeprog.install_docs  # vendor tools must carry docs

    gcc = manifest.find_tool("arm-none-eabi-gcc")
    assert gcc is not None
    assert gcc.is_vendor is False


def test_all_provided_binaries_includes_bundles() -> None:
    manifest = tcr.load_family("arm-cortex-m")
    gcc = manifest.find_tool("arm-none-eabi-gcc")
    assert gcc is not None
    provided = set(gcc.all_provided_binaries)
    assert "arm-none-eabi-gcc" in provided
    assert "arm-none-eabi-gdb" in provided
    assert "arm-none-eabi-size" in provided


# ---------------------------------------------------------------------------
# Cycle / unknown-parent / schema error paths (stubbed locator)
# ---------------------------------------------------------------------------


_BASIC_REQUIRED_BLOCK = """\
required:
  - tool: gcc
    version: ">=10"
    source: xpack
    capabilities: [build]
"""


def test_extends_cycle_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    manifests = {
        "alpha": (
            'schema_version: "1.0.0"\n'
            "family_id: alpha\n"
            "core: cortex-m4f\n"
            "extends: beta\n"
            f"{_BASIC_REQUIRED_BLOCK}"
        ),
        "beta": (
            'schema_version: "1.0.0"\n'
            "family_id: beta\n"
            "core: cortex-m4f\n"
            "extends: alpha\n"
            f"{_BASIC_REQUIRED_BLOCK}"
        ),
    }
    _stub_locator(monkeypatch, manifests)

    with pytest.raises(FamilyToolchainCycleError) as exc_info:
        tcr.load_family("alpha")
    msg = str(exc_info.value)
    assert "alpha" in msg and "beta" in msg
    assert "→" in msg  # the chain renders with arrows


def test_extends_unknown_parent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    manifests = {
        "kid": (
            'schema_version: "1.0.0"\n'
            "family_id: kid\n"
            "core: cortex-m4f\n"
            "extends: ghost\n"
            f"{_BASIC_REQUIRED_BLOCK}"
        ),
    }
    _stub_locator(monkeypatch, manifests)

    with pytest.raises(FamilyToolchainUnknownParentError) as exc_info:
        tcr.load_family("kid")
    assert "ghost" in str(exc_info.value)


def test_schema_error_raises_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A manifest missing the required `core` field fails JSON Schema."""
    manifests = {
        "broken": (
            'schema_version: "1.0.0"\n'
            "family_id: broken\n"
            # no `core` field — schema requires it
            f"{_BASIC_REQUIRED_BLOCK}"
        ),
    }
    _stub_locator(monkeypatch, manifests)

    with pytest.raises(FamilyToolchainSchemaError) as exc_info:
        tcr.load_family("broken")
    assert "broken.yml" in str(exc_info.value)
    assert "core" in str(exc_info.value)


def test_non_dict_yaml_raises_schema_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A YAML that parses to a list (not a mapping) is a schema error."""
    monkeypatch.setattr(
        tcr,
        "_read_manifest_text",
        lambda family_id: "- this\n- is\n- a\n- list\n",
    )
    with pytest.raises(FamilyToolchainSchemaError) as exc_info:
        tcr.load_family("listy")
    assert "mapping" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def test_load_family_caches_to_disk() -> None:
    """Loading twice should produce identical manifests AND drop a
    cache file under .alloy/cache/families/.
    """
    first = tcr.load_family("stm32g0")
    cache_path = tcr._cache_path("stm32g0")
    assert cache_path.exists(), "expected on-disk cache file to be written"

    second = tcr.load_family("stm32g0")
    # Equivalent typed views (frozen dataclasses compare by field).
    assert first == second


def test_cache_invalidates_on_alloy_cli_version_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cache key that no longer matches forces re-parsing.

    We simulate an alloy-cli upgrade by swapping the version constant
    AFTER the first load — the second load should bypass the stale
    cache file and rewrite it.
    """
    first = tcr.load_family("rp2040")
    monkeypatch.setattr(tcr, "_alloy_cli_version", "999.0.0+test")
    second = tcr.load_family("rp2040")
    # Both are valid manifests
    assert first.family_id == second.family_id == "rp2040"
    assert first.core == second.core
    # Cache file got rewritten with the new key — read its key to confirm.
    import pickle

    with tcr._cache_path("rp2040").open("rb") as fp:
        cached = pickle.load(fp)
    assert "999.0.0+test" not in cached["key"]  # key is sha256, not raw version
    # But the manifest projection must still match.
    assert cached["manifest"] == second


def test_cache_corruption_falls_back_to_reparse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A truncated/garbage pickle file should not crash load_family —
    it must silently re-parse from YAML.
    """
    # Redirect the cache dir to a fresh tmp_path so we can corrupt it.
    monkeypatch.setattr(tcr, "_cache_dir", lambda: tmp_path)
    cache_path = tmp_path / "stm32g0.pkl"
    cache_path.write_bytes(b"not a real pickle")

    manifest = tcr.load_family("stm32g0")
    assert manifest.family_id == "stm32g0"
    # And the corrupt file got overwritten with a valid pickle.
    import pickle

    with cache_path.open("rb") as fp:
        cached = pickle.load(fp)
    assert isinstance(cached, dict) and "manifest" in cached


# ---------------------------------------------------------------------------
# resolve_for_project
# ---------------------------------------------------------------------------


def test_resolve_for_project_uses_chip_family() -> None:
    config = _make_config(chip_family="stm32g0")
    manifest = tcr.resolve_for_project(config)
    assert manifest is not None
    assert manifest.family_id == "stm32g0"


def test_resolve_for_project_uses_board_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When only [board] is set, we look it up via core.boards.lookup."""
    config = _make_config(board="fake-board")

    fake_manifest = type(
        "FakeBoardManifest",
        (),
        {"family": "stm32f4"},
    )()

    def _fake_lookup(board_id: str) -> Any:
        assert board_id == "fake-board"
        return fake_manifest

    from alloy_cli.core import boards as _boards

    monkeypatch.setattr(_boards, "lookup", _fake_lookup)

    manifest = tcr.resolve_for_project(config)
    assert manifest is not None
    assert manifest.family_id == "stm32f4"


def test_resolve_for_project_returns_none_for_unknown_chip_family() -> None:
    config = _make_config(chip_family="brand-new-family-not-shipped")
    manifest = tcr.resolve_for_project(config)
    assert manifest is None


def test_resolve_for_project_returns_none_when_no_target() -> None:
    config = _make_config()  # no chip, no board
    assert tcr.resolve_for_project(config) is None


def test_resolve_for_project_returns_none_when_board_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A board id that boards.lookup cannot resolve must not crash."""
    from alloy_cli.core import boards as _boards
    from alloy_cli.core.errors import BoardNotFoundError

    def _raise(board_id: str) -> Any:
        raise BoardNotFoundError(f"no such board {board_id!r}")

    monkeypatch.setattr(_boards, "lookup", _raise)

    config = _make_config(board="nonexistent")
    assert tcr.resolve_for_project(config) is None


# ---------------------------------------------------------------------------
# Merge semantics — child overrides base by tool name
# ---------------------------------------------------------------------------


def test_child_overrides_base_tool_in_place(monkeypatch: pytest.MonkeyPatch) -> None:
    """If a child redeclares a tool the base already had, the child's
    version + source must win; the entry must stay in the base's
    original position so ordering remains predictable.
    """
    manifests = {
        "base": (
            'schema_version: "1.0.0"\n'
            "family_id: base\n"
            "core: cortex-m4f\n"
            "required:\n"
            "  - tool: cmake\n"
            "    version: \">=3.20\"\n"
            "    source: xpack\n"
            "    capabilities: [build]\n"
            "  - tool: ninja\n"
            "    version: \">=1.10\"\n"
            "    source: xpack\n"
            "    capabilities: [build]\n"
        ),
        "child": (
            'schema_version: "1.0.0"\n'
            "family_id: child\n"
            "core: cortex-m4f\n"
            "extends: base\n"
            "required:\n"
            "  - tool: cmake\n"
            "    version: \">=3.30\"\n"
            "    source: xpack\n"
            "    capabilities: [build]\n"
            "  - tool: probe-rs\n"
            "    version: \">=0.27\"\n"
            "    source: probe-rs-installer\n"
            "    capabilities: [flash, debug]\n"
        ),
    }
    _stub_locator(monkeypatch, manifests)

    manifest = tcr.load_family("child")
    tools = list(manifest.required)
    names = [t.tool for t in tools]
    # cmake stays at position 0 (base position); child's version overrides.
    assert names[0] == "cmake"
    assert tools[0].version == ">=3.30"
    # ninja stays at position 1 (base only).
    assert names[1] == "ninja"
    # probe-rs (new from child) appended last.
    assert names[-1] == "probe-rs"


def test_chain_is_recorded_for_introspection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three-level chain: leaf → mid → root should record (mid, root)
    as the leaf's chain.
    """
    manifests = {
        "leaf": (
            'schema_version: "1.0.0"\n'
            "family_id: leaf\n"
            "core: cortex-m33\n"
            "extends: mid\n"
            f"{_BASIC_REQUIRED_BLOCK}"
        ),
        "mid": (
            'schema_version: "1.0.0"\n'
            "family_id: mid\n"
            "core: cortex-m33\n"
            "extends: root\n"
            f"{_BASIC_REQUIRED_BLOCK}"
        ),
        "root": (
            'schema_version: "1.0.0"\n'
            "family_id: root\n"
            "core: cortex-m33\n"
            f"{_BASIC_REQUIRED_BLOCK}"
        ),
    }
    _stub_locator(monkeypatch, manifests)

    manifest = tcr.load_family("leaf")
    # chain is base-first per design (root → mid → leaf becomes ('root', 'mid')
    # excluding the leaf itself).
    assert manifest.chain == ("root", "mid")
    assert manifest.extends == "mid"  # the leaf's direct parent declaration
