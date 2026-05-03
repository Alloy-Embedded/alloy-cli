"""Tests for the Wave-2 MCP read-only tools.

Spec scenarios pinned here (from
``openspec/changes/add-toolchain-installer/specs/mcp-surface/spec.md``):

  * ``toolchain_status`` reports installed / missing / vendor state.
  * ``toolchain_install_plan`` returns plan + skipped_vendor + total
    size; performs no I/O.
  * Unknown family → Wave-1 ``family-toolchain-not-found`` envelope
    with ``known_families``.
  * Unsupported host → ``family-toolchain-installer-unsupported-host``
    envelope with ``host`` + ``supported_hosts``.
  * Both tools appear in ``registry.names()``.
  * Neither tool calls the downloader.
"""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pytest

from alloy_cli.core import tool_sources as _ts
from alloy_cli.core import toolchain_manager as _tm
from alloy_cli.core.process import FakeRunner
from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact
from alloy_cli.mcp import ToolError, ToolRegistry, build_default_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets a fresh store under tmp_path."""
    root = tmp_path / "store"
    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(root / "tools"))
    return root


@pytest.fixture
def registry(tmp_path: Path) -> ToolRegistry:
    return build_default_registry(project_dir=tmp_path, runner=FakeRunner())


def _sha_of(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _install_arm_gcc(tmp_path: Path, *, version: str = "14.2.1-1.1") -> str:
    src = tmp_path / "_pkg" / f"xpack-arm-none-eabi-gcc-{version}" / "bin"
    src.mkdir(parents=True, exist_ok=True)
    for binary in ("arm-none-eabi-gcc", "arm-none-eabi-gdb"):
        (src / binary).write_text("#!/bin/sh\n", encoding="utf-8")
    archive = tmp_path / f"arm-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(
            tmp_path / "_pkg" / f"xpack-arm-none-eabi-gcc-{version}",
            arcname=f"xpack-arm-none-eabi-gcc-{version}",
        )
    sha = _sha_of(archive.read_bytes())

    artefact = SourceArtifact(
        tool="arm-none-eabi-gcc",
        version=version,
        source="xpack",
        url=f"https://example.com/arm-{version}.tar.gz",
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir=f"xpack-arm-none-eabi-gcc-{version}",
        binaries=("bin/arm-none-eabi-gcc", "bin/arm-none-eabi-gdb"),
    )
    fake_dl = FakeDownloader()
    fake_dl.expect(artefact.url, archive)
    _tm.install(artefact, downloader=fake_dl)
    return sha


# ---------------------------------------------------------------------------
# Discoverability
# ---------------------------------------------------------------------------


def test_both_tools_appear_in_registry(registry: ToolRegistry) -> None:
    names = registry.names()
    assert "toolchain_status" in names
    assert "toolchain_install_plan" in names


def test_tool_descriptions_are_non_empty(registry: ToolRegistry) -> None:
    for name in ("toolchain_status", "toolchain_install_plan"):
        tool = registry.get_tool(name)
        assert tool.description, f"{name} description is empty"


def test_parameter_schemas_match_spec(registry: ToolRegistry) -> None:
    status_schema = dict(registry.get_tool("toolchain_status").parameter_schema)
    plan_schema = dict(registry.get_tool("toolchain_install_plan").parameter_schema)
    assert status_schema == {"family_id": "string?"}
    assert plan_schema == {"family_id": "string"}


# ---------------------------------------------------------------------------
# toolchain_status
# ---------------------------------------------------------------------------


def test_toolchain_status_reports_installed_vs_missing_vs_vendor(
    registry: ToolRegistry, tmp_path: Path
) -> None:
    _install_arm_gcc(tmp_path)

    payload = registry.call("toolchain_status", family_id="stm32g0")
    assert payload["family_id"] == "stm32g0"
    assert payload["core"] == "cortex-m0plus"
    assert payload["host"]  # populated for the active host

    by_tool = {row["tool"]: row for row in payload["tools"]}

    # arm-gcc is installed (we just put it there)
    arm = by_tool["arm-none-eabi-gcc"]
    assert arm["state"] == "ok"
    assert arm["installed"] is True
    assert arm["installed_version"] == "14.2.1-1.1"
    assert arm["installed_path"]
    # Wave-1 fields preserved
    assert arm["source"] == "xpack"
    assert arm["udev_required"] is False
    assert "build" in arm["capabilities"]

    # cmake / ninja / probe-rs are missing
    for tool in ("cmake", "ninja", "probe-rs"):
        row = by_tool[tool]
        assert row["state"] == "missing"
        assert row["installed"] is False
        assert row["installed_path"] is None

    # STM32CubeProgrammer is vendor — never installed, never missing
    cube = by_tool["STM32CubeProgrammer"]
    assert cube["state"] == "vendor"
    assert cube["installed"] is False
    assert cube["source"] == "vendor"


def test_toolchain_status_carries_tier_per_tool(registry: ToolRegistry) -> None:
    payload = registry.call("toolchain_status", family_id="stm32g0")
    by_tool = {row["tool"]: row for row in payload["tools"]}
    # required tools (inherited from arm-cortex-m base)
    for tool in ("arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"):
        assert by_tool[tool]["tier"] == "required"
    # recommended tools (from stm32g0 manifest)
    for tool in ("STM32CubeProgrammer", "dfu-util", "tio"):
        assert by_tool[tool]["tier"] == "recommended"


def test_toolchain_status_falls_back_to_project_when_family_omitted(
    registry: ToolRegistry, tmp_path: Path
) -> None:
    """Without family_id, the resolver looks at the project's
    alloy.toml.  When no project exists, surface a typed
    missing-target envelope.
    """
    with pytest.raises(ToolError) as exc_info:
        registry.call("toolchain_status")
    assert exc_info.value.error_type == "missing-target"


def test_toolchain_status_unknown_family_returns_wave1_envelope(
    registry: ToolRegistry,
) -> None:
    with pytest.raises(ToolError) as exc_info:
        registry.call("toolchain_status", family_id="nonexistent")
    err = exc_info.value
    assert err.error_type == "family-toolchain-not-found"
    envelope = err.to_dict()
    assert "known_families" in envelope
    for fid in ("arm-cortex-m", "esp32", "nrf52", "rp2040", "stm32f4", "stm32g0"):
        assert fid in envelope["known_families"]


# ---------------------------------------------------------------------------
# toolchain_install_plan
# ---------------------------------------------------------------------------


def test_install_plan_for_stm32g0_returns_full_plan(
    registry: ToolRegistry,
) -> None:
    payload = registry.call("toolchain_install_plan", family_id="stm32g0")
    assert payload["family_id"] == "stm32g0"
    # Host is reported as a dict {os, arch}
    assert "os" in payload["host"]
    assert "arch" in payload["host"]

    plan = payload["plan"]
    assert isinstance(plan, list)
    plan_tools = {entry["tool"] for entry in plan}
    # All non-vendor tools land in plan
    assert {"arm-none-eabi-gcc", "cmake", "ninja", "probe-rs", "tio", "dfu-util"} <= plan_tools
    # Vendor tool does NOT land in plan
    assert "STM32CubeProgrammer" not in plan_tools


def test_install_plan_entries_carry_url_sha_size(
    registry: ToolRegistry,
) -> None:
    payload = registry.call("toolchain_install_plan", family_id="stm32g0")
    for entry in payload["plan"]:
        assert "url" in entry
        assert entry["url"].startswith("https://")
        assert "sha256" in entry
        assert len(entry["sha256"]) == 64
        # size_bytes may be None (when pin file doesn't declare size)
        assert "size_bytes" in entry


def test_install_plan_skipped_vendor_carries_install_doc_url(
    registry: ToolRegistry,
) -> None:
    payload = registry.call("toolchain_install_plan", family_id="stm32g0")
    skipped = payload["skipped_vendor"]
    assert len(skipped) >= 1
    cube = next(s for s in skipped if s["tool"] == "STM32CubeProgrammer")
    assert cube["install_doc_url"]
    assert cube["install_doc_url"].startswith("https://")
    assert "st.com" in cube["install_doc_url"].lower()


def test_install_plan_total_size_is_sum_of_entries(
    registry: ToolRegistry,
) -> None:
    payload = registry.call("toolchain_install_plan", family_id="stm32g0")
    expected = sum((entry.get("size_bytes") or 0) for entry in payload["plan"])
    assert payload["total_size_bytes"] == expected


def test_install_plan_unknown_family_returns_envelope(
    registry: ToolRegistry,
) -> None:
    with pytest.raises(ToolError) as exc_info:
        registry.call("toolchain_install_plan", family_id="nonexistent")
    err = exc_info.value
    assert err.error_type == "family-toolchain-not-found"
    envelope = err.to_dict()
    assert "known_families" in envelope


def test_install_plan_unsupported_host_returns_envelope(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the active host triple has no pin in any of the family's
    tools, install_plan surfaces the typed envelope with host +
    supported_hosts.
    """
    # Force host_triple() to raise UnsupportedHost
    from alloy_cli.core.errors import (
        FamilyToolchainInstallerUnsupportedHostError,
    )

    def _bad_host() -> _ts.HostTriple:
        raise FamilyToolchainInstallerUnsupportedHostError(
            "test: platform.system()='FreeBSD' platform.machine()='sparc64'"
        )

    monkeypatch.setattr(_ts, "host_triple", _bad_host)

    with pytest.raises(ToolError) as exc_info:
        registry.call("toolchain_install_plan", family_id="stm32g0")
    err = exc_info.value
    assert err.error_type == "family-toolchain-installer-unsupported-host"
    envelope = err.to_dict()
    assert "host" in envelope
    # supported_hosts is the union of every host triple any tool's pin
    # file declares for stm32g0's required + recommended.
    assert "supported_hosts" in envelope
    # canonical hosts must be in the list
    for host in ("linux-x86_64", "macos-arm64"):
        assert host in envelope["supported_hosts"]


def test_install_plan_does_not_call_downloader(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec contract: install_plan performs no I/O.  Replacing the
    downloader with one that explodes verifies the call path never
    touches it.
    """
    from alloy_cli.core.errors import FamilyToolchainInstallerDownloadError

    class _ExplodingDownloader:
        def fetch(self, *_args, **_kwargs):
            raise FamilyToolchainInstallerDownloadError(
                "downloader was unexpectedly invoked"
            )

    restore = _ts.configure_downloader(_ExplodingDownloader())
    try:
        # Should NOT raise
        payload = registry.call("toolchain_install_plan", family_id="stm32g0")
        assert payload["plan"]
    finally:
        restore()


def test_toolchain_status_does_not_call_downloader(
    registry: ToolRegistry,
) -> None:
    """Same contract for status — purely reads from the local manifest."""
    from alloy_cli.core.errors import FamilyToolchainInstallerDownloadError

    class _ExplodingDownloader:
        def fetch(self, *_args, **_kwargs):
            raise FamilyToolchainInstallerDownloadError("nope")

    restore = _ts.configure_downloader(_ExplodingDownloader())
    try:
        payload = registry.call("toolchain_status", family_id="stm32g0")
        assert payload["family_id"] == "stm32g0"
    finally:
        restore()


# ---------------------------------------------------------------------------
# JSON-friendliness
# ---------------------------------------------------------------------------


def test_install_plan_response_is_json_serialisable(
    registry: ToolRegistry,
) -> None:
    import json as _json

    payload = registry.call("toolchain_install_plan", family_id="stm32g0")
    blob = _json.dumps(payload, sort_keys=True)
    assert _json.loads(blob) == payload


def test_status_response_is_json_serialisable(
    registry: ToolRegistry,
) -> None:
    import json as _json

    payload = registry.call("toolchain_status", family_id="stm32g0")
    blob = _json.dumps(payload, sort_keys=True)
    assert _json.loads(blob) == payload


# ---------------------------------------------------------------------------
# Wave-3 mutating tool: toolchain_apply_install_plan
# ---------------------------------------------------------------------------


def _stub_install_family(monkeypatch: pytest.MonkeyPatch, *, failed_tools=()):
    """Replace ``install_family`` in the MCP module with a recorder."""
    from dataclasses import replace

    from alloy_cli.core import tool_sources as _ts_inner
    from alloy_cli.core import toolchain_orchestrator as _orch
    from alloy_cli.core.toolchain_orchestrator import (
        InstallOutcome,
        InstallReport,
    )
    from alloy_cli.mcp import tools as _mcp_tools

    captured: dict = {"calls": []}

    def _fake(manifest, *, project_root=None, on_event=None, **kwargs):
        captured["calls"].append(
            {
                "family_id": manifest.family_id,
                "project_root": project_root,
                "tool_count": (
                    len(manifest.required) + len(manifest.recommended)
                ),
            }
        )
        outcomes = []
        for tool in (*manifest.required, *manifest.recommended):
            if tool.is_vendor:
                outcomes.append(
                    InstallOutcome(
                        tool=tool.tool,
                        version=tool.version,
                        state="skipped-vendor",
                        install_doc_url="https://example.com/vendor-doc",
                    )
                )
                continue
            failed = tool.tool in failed_tools
            outcomes.append(
                InstallOutcome(
                    tool=tool.tool,
                    version=tool.version,
                    state="failed" if failed else "installed",
                    sha256=None if failed else "deadbeef" * 8,
                    bytes_downloaded=0 if failed else 1024,
                    error_type=("family-toolchain-installer-checksum" if failed else None),
                    error_message=("checksum mismatch" if failed else None),
                )
            )
        return InstallReport(
            family_id=manifest.family_id,
            host=replace(_ts_inner.host_triple()),
            outcomes=tuple(outcomes),
            total_bytes_downloaded=sum(o.bytes_downloaded for o in outcomes),
            lockfile_updated=any(o.installed for o in outcomes) and project_root is not None,
            lockfile_path=(project_root / ".alloy" / "toolchain.lock") if project_root else None,
        )

    monkeypatch.setattr(_mcp_tools._orch, "install_family", _fake)
    monkeypatch.setattr(_orch, "install_family", _fake)
    return captured


def test_apply_install_plan_appears_in_registry(registry: ToolRegistry) -> None:
    assert "toolchain_apply_install_plan" in registry.names()


def test_apply_install_plan_returns_outcomes_for_every_tier_entry(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One row per tool the family declares — required + recommended."""
    captured = _stub_install_family(monkeypatch)
    payload = registry.call("toolchain_apply_install_plan", family_id="stm32g0")
    assert payload["family_id"] == "stm32g0"
    assert isinstance(payload["outcomes"], list)
    tools_in_response = {row["tool"] for row in payload["outcomes"]}
    # Required tier (inherited from arm-cortex-m): cmake, ninja,
    # arm-none-eabi-gcc, probe-rs.  Recommended for stm32g0:
    # tio + STM32CubeProgrammer (vendor).
    for tool in ("arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"):
        assert tool in tools_in_response
    assert "STM32CubeProgrammer" in tools_in_response
    assert len(captured["calls"]) == 1
    assert captured["calls"][0]["family_id"] == "stm32g0"


def test_apply_install_plan_vendor_row_carries_skipped_and_install_doc(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vendor tools NEVER spawn a download; the row carries
    ``skipped=true, reason="vendor"`` and the install_doc_url."""
    _stub_install_family(monkeypatch)
    payload = registry.call("toolchain_apply_install_plan", family_id="stm32g0")
    cube = next(
        (r for r in payload["outcomes"] if r["tool"] == "STM32CubeProgrammer"),
        None,
    )
    assert cube is not None
    assert cube["skipped"] is True
    assert cube["reason"] == "vendor"
    assert cube["install_doc_url"] is not None
    assert cube["bytes_downloaded"] == 0


def test_apply_install_plan_failed_row_carries_typed_error_type(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-tool failure surfaces with state='failed' and the typed
    error_type — the rest of the walk completes regardless."""
    _stub_install_family(monkeypatch, failed_tools=("cmake",))
    payload = registry.call("toolchain_apply_install_plan", family_id="stm32g0")
    cmake = next(r for r in payload["outcomes"] if r["tool"] == "cmake")
    assert cmake["state"] == "failed"
    assert cmake["reason"] == "failed"
    assert cmake["error_type"] == "family-toolchain-installer-checksum"
    # Other tools still attempted.
    other_states = {r["tool"]: r["state"] for r in payload["outcomes"] if r["tool"] != "cmake"}
    assert "arm-none-eabi-gcc" in other_states
    assert other_states["arm-none-eabi-gcc"] == "installed"


def test_apply_install_plan_unknown_family_raises_typed_envelope(
    registry: ToolRegistry,
) -> None:
    """Unknown family → Wave-1 envelope with ``known_families``."""
    with pytest.raises(ToolError) as excinfo:
        registry.call("toolchain_apply_install_plan", family_id="not-a-family")
    err = excinfo.value
    assert err.error_type == "family-toolchain-not-found"
    assert "known_families" in (err.detail or {})


def test_apply_install_plan_response_carries_aggregate_counts(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The response carries aggregated counters the agent uses for
    summarising progress to the user."""
    _stub_install_family(monkeypatch)
    payload = registry.call("toolchain_apply_install_plan", family_id="stm32g0")
    for key in (
        "installed_count",
        "failed_count",
        "total_bytes_downloaded",
        "lockfile_updated",
        "lockfile_path",
    ):
        assert key in payload, f"response missing aggregate key {key!r}"
    assert isinstance(payload["installed_count"], int)
    assert isinstance(payload["failed_count"], int)


def test_apply_install_plan_response_is_json_serialisable(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json as _json

    _stub_install_family(monkeypatch)
    payload = registry.call("toolchain_apply_install_plan", family_id="stm32g0")
    blob = _json.dumps(payload, sort_keys=True)
    assert _json.loads(blob) == payload


def test_apply_install_plan_lockfile_path_is_under_project_dir(
    registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the orchestrator writes the lockfile, the response path
    points inside the project_dir of the registry."""
    _stub_install_family(monkeypatch)
    payload = registry.call("toolchain_apply_install_plan", family_id="stm32g0")
    if payload["lockfile_updated"]:
        assert payload["lockfile_path"] is not None
        assert ".alloy/toolchain.lock" in payload["lockfile_path"]


def test_system_prompt_documents_two_phase_pattern() -> None:
    """The opencode system prompt mentions both tools in the canonical
    workflow — keeps LLM agents aware of the preview-then-apply
    contract."""
    prompt = (
        Path(__file__).resolve().parents[1]
        / "src/alloy_cli/integrations/opencode/system_prompt.md"
    ).read_text(encoding="utf-8")
    assert "toolchain_install_plan" in prompt
    assert "toolchain_apply_install_plan" in prompt
    assert "two-phase" in prompt.lower() or "two phase" in prompt.lower()
