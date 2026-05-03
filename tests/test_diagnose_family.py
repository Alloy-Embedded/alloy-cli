"""Tests for the family-aware ``core.diagnose.run`` extension.

Covers the spec scenarios in
``openspec/changes/add-toolchain-registry/specs/cli-surface/spec.md``:

  * doctor inside a stm32g0 project lists only stm32g0 tools
  * `family="esp32"` lists espressif tools (no arm-gcc)
  * vendor-source missing renders as info, not error
  * unknown family override surfaces an error row + known list
  * unknown family from project resolution falls back with an info note
  * `--json` output carries the new `source` field on every entry
  * legacy callers (no family) see the same checks pre-Wave-1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core import toolchain_registry as _registry
from alloy_cli.core.project import (
    SCHEMA_VERSION,
    BoardRef,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_chip_project(tmp_path: Path, *, vendor: str, family: str, device: str) -> Path:
    """Write a minimal alloy.toml that pins a specific chip family."""
    config = ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name="demo"),
        board=None,
        chip=ChipRef(vendor=vendor, family=family, device=device),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    write(tmp_path / "alloy.toml", config)
    return tmp_path


def _seed_board_project(tmp_path: Path, *, board_id: str) -> Path:
    config = ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name="demo"),
        board=BoardRef(id=board_id),
        chip=None,
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    write(tmp_path / "alloy.toml", config)
    return tmp_path


def _stub_toolchains_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every dedicated detector report "not on PATH".

    Exercises the missing-tool branches without depending on what is
    or isn't actually installed in the contributor's environment.
    """

    def _missing(name: str) -> _toolchain.ToolchainStatus:
        return _toolchain.ToolchainStatus(
            name=name,
            present=False,
            version=None,
            path=None,
            install_hint=f"install {name}",
        )

    monkeypatch.setattr(_toolchain, "detect_arm_gcc", lambda: _missing("arm-none-eabi-gcc"))
    monkeypatch.setattr(_toolchain, "detect_cmake", lambda: _missing("cmake"))
    monkeypatch.setattr(_toolchain, "detect_ninja", lambda: _missing("ninja"))
    monkeypatch.setattr(_toolchain, "detect_probe_rs", lambda: _missing("probe-rs"))
    monkeypatch.setattr(_toolchain, "detect_openocd", lambda: _missing("openocd"))


def _stub_shutil_which(
    monkeypatch: pytest.MonkeyPatch, present: set[str] | None = None
) -> None:
    """Force the generic-tool dispatcher into the missing branch."""
    present = present or set()
    monkeypatch.setattr(
        _diagnose.shutil,
        "which",
        lambda name: f"/fake/{name}" if name in present else None,
    )


def _names(report: _diagnose.DiagnosticReport) -> set[str]:
    return {c.name for c in report.checks}


def _by_name(report: _diagnose.DiagnosticReport, name: str) -> _diagnose.CheckResult:
    matches = [c for c in report.checks if c.name == name]
    assert matches, f"no check named {name!r}; have {sorted(_names(report))}"
    assert len(matches) == 1, f"expected unique check {name!r}, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# Family resolution from project
# ---------------------------------------------------------------------------


def test_doctor_inside_stm32g0_project_lists_only_stm32g0_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_chip_project(tmp_path, vendor="st", family="stm32g0", device="stm32g071rb")
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)  # nothing on PATH

    report = _diagnose.run(project_dir=tmp_path)
    names = _names(report)

    # Required base tools (inherited from arm-cortex-m)
    for tool in ("arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"):
        assert tool in names, f"{tool} should appear for stm32g0"

    # Recommended stm32g0-specific tool
    assert "STM32CubeProgrammer" in names

    # NOT present — these belong to other families
    assert "xtensa-esp-elf-gcc" not in names
    assert "esptool" not in names
    assert "picotool" not in names
    assert "nrfjprog" not in names


def test_doctor_inside_project_with_unmapped_family_falls_back_with_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Project pins a family alloy-cli doesn't ship a manifest for —
    doctor surfaces an info row AND runs the legacy generic checks.
    """
    _seed_chip_project(
        tmp_path, vendor="st", family="stm32xyz-not-shipped", device="stm32xyz123"
    )
    _stub_toolchains_missing(monkeypatch)

    report = _diagnose.run(project_dir=tmp_path)
    names = _names(report)

    # Soft-warning row exists and explains the fallback.
    assert "toolchain-family" in names
    note = _by_name(report, "toolchain-family")
    assert note.severity == "info"
    assert "stm32xyz-not-shipped" in note.message
    assert "falling back" in note.message.lower()

    # Legacy generic checks ran
    for tool in ("cmake", "ninja", "arm-none-eabi-gcc", "probe-rs"):
        assert tool in names


# ---------------------------------------------------------------------------
# --for override
# ---------------------------------------------------------------------------


def test_explicit_family_override_for_esp32_lists_espressif_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No project, just `family="esp32"` — shows xtensa-gcc + esptool, no arm-gcc."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    report = _diagnose.run(project_dir=tmp_path, family="esp32")
    names = _names(report)

    assert "xtensa-esp-elf-gcc" in names
    assert "esptool" in names
    assert "cmake" in names
    assert "ninja" in names
    assert "tio" in names

    # Cortex-M tools must NOT appear (esp32 doesn't extend arm-cortex-m)
    assert "arm-none-eabi-gcc" not in names
    assert "probe-rs" not in names
    assert "STM32CubeProgrammer" not in names


def test_unknown_family_override_surfaces_error_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_toolchains_missing(monkeypatch)

    report = _diagnose.run(project_dir=tmp_path, family="nonexistent-family-xyz")
    note = _by_name(report, "toolchain-family")
    assert note.ok is False
    assert note.severity == "error"
    assert "nonexistent-family-xyz" in note.message
    assert note.install_hint and "Known families" in note.install_hint
    # And we still ran the legacy generic checks so the user sees what's
    # missing on their machine regardless of the family lookup failure.
    assert "cmake" in _names(report)


# ---------------------------------------------------------------------------
# Vendor-source missing renders as info, not error
# ---------------------------------------------------------------------------


def test_vendor_source_missing_tool_is_info_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """STM32CubeProgrammer is `source: vendor` on stm32f4 — when missing,
    it must NOT block the doctor exit code AND must carry an install
    doc URL.
    """
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)  # nothing on PATH, including STM32CubeProgrammer

    report = _diagnose.run(project_dir=tmp_path, family="stm32f4")
    cube = _by_name(report, "STM32CubeProgrammer")

    assert cube.ok is False
    assert cube.severity == "info"  # NOT error
    assert cube.source == "vendor (EULA — install manually)"
    assert cube.install_hint
    assert cube.install_hint.startswith("https://")
    # Contains a recognisable st.com domain
    assert "st.com" in cube.install_hint.lower()


def test_vendor_source_missing_does_not_set_has_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`alloy doctor` must not exit non-zero just because a vendor tool
    is missing — vendor downloads are EULA-gated, not errors.
    """
    # stub away every dedicated detector + everything off PATH
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)
    # but pretend the dedicated tools (gcc/cmake/ninja/probe-rs) are
    # actually present so the only "missing" tools are the recommended
    # vendor / generic ones.
    monkeypatch.setattr(
        _toolchain,
        "detect_arm_gcc",
        lambda: _toolchain.ToolchainStatus(
            name="arm-none-eabi-gcc",
            present=True,
            version="14.2.0",
            path="/fake/arm-none-eabi-gcc",
            install_hint=None,
        ),
    )
    monkeypatch.setattr(
        _toolchain,
        "detect_cmake",
        lambda: _toolchain.ToolchainStatus(
            name="cmake", present=True, version="3.30.0", path="/fake/cmake", install_hint=None
        ),
    )
    monkeypatch.setattr(
        _toolchain,
        "detect_ninja",
        lambda: _toolchain.ToolchainStatus(
            name="ninja", present=True, version="1.12.0", path="/fake/ninja", install_hint=None
        ),
    )
    monkeypatch.setattr(
        _toolchain,
        "detect_probe_rs",
        lambda: _toolchain.ToolchainStatus(
            name="probe-rs",
            present=True,
            version="0.27.0",
            path="/fake/probe-rs",
            install_hint=None,
        ),
    )

    report = _diagnose.run(project_dir=tmp_path, family="stm32f4")
    # Filter to just toolchain-y checks; the project / submodule
    # checks may legitimately fail in tmp_path so we don't assert
    # has_errors directly.
    cube = _by_name(report, "STM32CubeProgrammer")
    assert cube.severity == "info"
    assert cube.ok is False
    # The CHECK is not OK, but it is not an error severity → doctor's
    # `has_errors` ignores it.
    only_toolchain_errors = [
        c for c in report.checks
        if c.severity == "error" and not c.ok
        and c.name in {"STM32CubeProgrammer", "dfu-util", "tio"}
    ]
    # dfu-util/tio are non-vendor github sources → they ARE errors when missing
    assert all(c.name != "STM32CubeProgrammer" for c in only_toolchain_errors)


# ---------------------------------------------------------------------------
# Detected-tool source field
# ---------------------------------------------------------------------------


def test_detected_tool_source_is_system(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a generic tool IS on PATH, source should be `system`."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch, present={"tio"})

    report = _diagnose.run(project_dir=tmp_path, family="stm32g0")
    tio = _by_name(report, "tio")
    assert tio.ok is True
    assert tio.severity == "info"
    assert tio.source == "system"


def test_dedicated_detector_present_uses_system_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tools with a dedicated `core.toolchain.detect_*` should also
    report `source="system"` when found.
    """
    monkeypatch.setattr(
        _toolchain,
        "detect_arm_gcc",
        lambda: _toolchain.ToolchainStatus(
            name="arm-none-eabi-gcc",
            present=True,
            version="14.2.0",
            path="/fake/arm-none-eabi-gcc",
            install_hint=None,
        ),
    )
    # everything else missing
    monkeypatch.setattr(
        _toolchain,
        "detect_cmake",
        lambda: _toolchain.ToolchainStatus(
            name="cmake", present=False, version=None, path=None, install_hint="install cmake"
        ),
    )
    monkeypatch.setattr(
        _toolchain,
        "detect_ninja",
        lambda: _toolchain.ToolchainStatus(
            name="ninja", present=False, version=None, path=None, install_hint="install ninja"
        ),
    )
    monkeypatch.setattr(
        _toolchain,
        "detect_probe_rs",
        lambda: _toolchain.ToolchainStatus(
            name="probe-rs", present=False, version=None, path=None, install_hint="install probe-rs"
        ),
    )
    _stub_shutil_which(monkeypatch)

    report = _diagnose.run(project_dir=tmp_path, family="stm32g0")
    gcc = _by_name(report, "arm-none-eabi-gcc")
    assert gcc.ok is True
    assert gcc.source == "system"
    # And missing dedicated detectors carry the manifest source for the column
    cmake = _by_name(report, "cmake")
    assert cmake.ok is False
    assert cmake.source == "xpack"


def test_non_vendor_missing_carries_manifest_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tio (`source: github:tio/tio`) should report that source string."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    report = _diagnose.run(project_dir=tmp_path, family="stm32g0")
    tio = _by_name(report, "tio")
    assert tio.ok is False
    assert tio.severity == "error"
    assert tio.source == "github:tio/tio"
    # Wave 3: the install_hint is now the concrete CLI command.
    assert tio.install_hint == "alloy toolchain install --for stm32g0 tio"
    assert tio.auto_fix == tio.install_hint


# ---------------------------------------------------------------------------
# JSON contract
# ---------------------------------------------------------------------------


def test_to_dict_bumps_schema_version_and_carries_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_chip_project(tmp_path, vendor="st", family="stm32g0", device="stm32g071rb")
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    payload = _diagnose.run(project_dir=tmp_path).to_dict()
    assert payload["schema_version"] == "1.1"

    checks = payload["checks"]
    assert isinstance(checks, list)

    # Every check entry — toolchain or otherwise — has a `source` key.
    for entry in checks:
        assert isinstance(entry, dict)
        assert "source" in entry, f"missing source on {entry.get('name')!r}"

    # Non-toolchain rows have source = None
    project_entry = next(c for c in checks if c["name"] == "alloy.toml")
    assert project_entry["source"] is None
    accessibility_entry = next(c for c in checks if c["name"] == "accessibility-suite")
    assert accessibility_entry["source"] is None


# ---------------------------------------------------------------------------
# Legacy compatibility
# ---------------------------------------------------------------------------


def test_legacy_generic_checks_run_when_no_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No project + no override → exactly the pre-Wave-1 generic check set."""
    _stub_toolchains_missing(monkeypatch)

    report = _diagnose.run(project_dir=tmp_path)
    names = _names(report)

    # The four generic toolchain rows
    assert {"cmake", "ninja", "arm-none-eabi-gcc", "probe-rs"} <= names

    # Plus the per-environment rows
    assert "alloy.toml" in names
    assert "alloy-devices-yml" in names
    assert "mcp" in names
    assert "accessibility-suite" in names

    # No family note in this path
    assert "toolchain-family" not in names

    # Source on legacy toolchain rows is None (legacy path doesn't know
    # the manifest source vocabulary).
    cmake = _by_name(report, "cmake")
    assert cmake.source is None


def test_resolve_family_for_run_uses_chip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_chip_project(tmp_path, vendor="st", family="stm32g0", device="stm32g071rb")
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    manifest, note = _diagnose._resolve_family_for_run(tmp_path, None)
    assert note is None
    assert manifest is not None
    assert manifest.family_id == "stm32g0"


def test_resolve_family_for_run_uses_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When [board] is set we look up the family via core.boards.lookup."""
    _seed_board_project(tmp_path, board_id="some-board")

    fake_board = type("FakeBoard", (), {"family": "rp2040"})()

    from alloy_cli.core import boards as _boards

    monkeypatch.setattr(_boards, "lookup", lambda _board_id: fake_board)

    manifest, note = _diagnose._resolve_family_for_run(tmp_path, None)
    assert note is None
    assert manifest is not None
    assert manifest.family_id == "rp2040"


def test_resolve_family_for_run_handles_missing_alloy_toml(tmp_path: Path) -> None:
    """No alloy.toml + no override → no manifest, no note."""
    manifest, note = _diagnose._resolve_family_for_run(tmp_path, None)
    assert manifest is None
    assert note is None


# ---------------------------------------------------------------------------
# Per-OS install doc
# ---------------------------------------------------------------------------


def test_per_os_install_doc_picks_active_os(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_req = _registry.ToolRequirement(
        tool="X",
        version=">=1",
        source="vendor",
        capabilities=("flash",),
        install_docs={
            "linux": "https://example.com/linux",
            "macos": "https://example.com/macos",
            "windows": "https://example.com/windows",
        },
    )

    monkeypatch.setattr(_diagnose.platform, "system", lambda: "Darwin")
    assert _diagnose._per_os_install_doc(tool_req) == "https://example.com/macos"

    monkeypatch.setattr(_diagnose.platform, "system", lambda: "Linux")
    assert _diagnose._per_os_install_doc(tool_req) == "https://example.com/linux"

    monkeypatch.setattr(_diagnose.platform, "system", lambda: "Windows")
    assert _diagnose._per_os_install_doc(tool_req) == "https://example.com/windows"


def test_per_os_install_doc_falls_back_to_any(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_req = _registry.ToolRequirement(
        tool="X",
        version=">=1",
        source="vendor",
        capabilities=("flash",),
        install_docs={"linux": "https://example.com/linux-only"},
    )
    monkeypatch.setattr(_diagnose.platform, "system", lambda: "Darwin")
    # No macOS doc, so we get the linux one as a fallback.
    assert _diagnose._per_os_install_doc(tool_req) == "https://example.com/linux-only"


def test_per_os_install_doc_returns_none_when_empty() -> None:
    tool_req = _registry.ToolRequirement(
        tool="X", version=">=1", source="vendor", capabilities=("flash",)
    )
    assert _diagnose._per_os_install_doc(tool_req) is None
