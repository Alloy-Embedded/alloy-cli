"""Wave-3 contract: ``alloy doctor --fix`` auto-installs missing
non-vendor toolchain tools through the shared orchestrator.

Pinned scenarios:

- Vendor-source rows are NEVER queued (already covered by
  ``test_run_fixes_skips_vendor_rows_in_auto_fix_pass`` — Wave 3
  reuses the same predicate).
- Required-tier missing tools dispatch through
  ``toolchain_orchestrator.install_family`` with a single-tool slice.
- Per-tool failure does not abort the rest of the queue.
- ``--with-recommended`` extends the queue to the recommended tier.
- Without a resolvable family the legacy ``alloy-devices-yml`` /
  ``mcp`` fixers still run.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core import process as _process
from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core import toolchain_orchestrator as _orch
from alloy_cli.core.diagnose import (
    AUTO_FIXERS,
    AutoFixOutcome,
    CheckResult,
    _auto_fix_install_toolchain_tool,
    _is_toolchain_install_row,
    get_auto_fix,
)
from alloy_cli.core.project import (
    SCHEMA_VERSION,
    ChipRef,
    ProjectConfig,
    ProjectMeta,
    write,
)
from alloy_cli.core.toolchain_orchestrator import InstallOutcome, InstallReport
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _stub_toolchains_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every dedicated detector into the missing branch."""

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


def _stub_shutil_which(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generic-tool dispatcher always reports missing."""
    monkeypatch.setattr(_diagnose.shutil, "which", lambda _name: None)


def _seed_chip_project(tmp_path: Path, *, family: str = "stm32g0") -> None:
    """Write an alloy.toml that pins ``family`` (st/<family>/stm32g071rb)."""
    config = ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name="fixture"),
        board=None,
        chip=ChipRef(vendor="st", family=family, device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    write(tmp_path / "alloy.toml", config)


# ---------------------------------------------------------------------------
# Predicate + registry
# ---------------------------------------------------------------------------


def test_toolchain_install_row_predicate_excludes_vendor() -> None:
    """Vendor rows have a ``vendor (EULA — install manually)`` source —
    the predicate must reject them so the auto-installer never fires."""
    vendor = CheckResult(
        name="STM32CubeProgrammer",
        ok=False,
        severity="info",
        message="missing",
        source="vendor (EULA — install manually)",
        auto_fix="manual",
    )
    assert _is_toolchain_install_row(vendor) is False


def test_toolchain_install_row_predicate_excludes_system() -> None:
    """A green ✓ row carries source='system' — the predicate skips it
    (already on PATH; nothing to install)."""
    happy = CheckResult(
        name="cmake",
        ok=True,
        severity="info",
        message="cmake 3.28 at /usr/bin/cmake",
        source="system",
    )
    assert _is_toolchain_install_row(happy) is False


def test_toolchain_install_row_predicate_includes_xpack_missing() -> None:
    """A missing tool with a manifest source (xpack, github:..., …) IS
    a toolchain row — that's the case the auto-installer handles."""
    miss = CheckResult(
        name="arm-none-eabi-gcc",
        ok=False,
        severity="error",
        message="not on PATH",
        source="xpack",
        auto_fix="alloy toolchain install --for stm32g0 arm-none-eabi-gcc",
    )
    assert _is_toolchain_install_row(miss) is True


def test_get_auto_fix_routes_toolchain_rows_to_sentinel() -> None:
    """Missing non-vendor toolchain rows → the sentinel-keyed fixer."""
    miss = CheckResult(
        name="arm-none-eabi-gcc",
        ok=False,
        severity="error",
        message="not on PATH",
        source="xpack",
        auto_fix="alloy toolchain install --for stm32g0 arm-none-eabi-gcc",
    )
    fixer = get_auto_fix(miss)
    assert fixer is _auto_fix_install_toolchain_tool


def test_auto_fixers_registry_includes_toolchain_sentinel() -> None:
    """The sentinel key MUST be in the registry — it's the dispatch
    point for every toolchain row."""
    assert "__toolchain_install__" in AUTO_FIXERS
    assert AUTO_FIXERS["__toolchain_install__"] is _auto_fix_install_toolchain_tool


# ---------------------------------------------------------------------------
# Auto-fixer error paths (no orchestrator dispatch)
# ---------------------------------------------------------------------------


def test_auto_fix_returns_failure_when_no_alloy_toml(tmp_path: Path) -> None:
    """No project context → the fixer reports a clean failure rather
    than blowing up with an exception."""
    check = CheckResult(
        name="cmake",
        ok=False,
        severity="error",
        message="missing",
        source="xpack",
        auto_fix="alloy toolchain install --for stm32g0 cmake",
    )
    outcome = _auto_fix_install_toolchain_tool(
        check, _process.runner, project_root=tmp_path
    )
    assert isinstance(outcome, AutoFixOutcome)
    assert outcome.ok is False
    assert "alloy.toml" in outcome.log


def test_auto_fix_returns_failure_when_tool_not_in_family(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking the fixer for a tool the resolved family doesn't declare
    is a clean failure — never an unhandled exception."""
    _seed_chip_project(tmp_path, family="stm32g0")
    check = CheckResult(
        name="picotool",  # belongs to rp2040, not stm32g0
        ok=False,
        severity="error",
        message="missing",
        source="github:raspberrypi/pico-sdk-tools",
        auto_fix="alloy toolchain install --for stm32g0 picotool",
    )
    outcome = _auto_fix_install_toolchain_tool(
        check, _process.runner, project_root=tmp_path
    )
    assert outcome.ok is False
    assert "picotool" in outcome.log
    assert "not declared" in outcome.log.lower() or "not in" in outcome.log.lower()


# ---------------------------------------------------------------------------
# Orchestrator dispatch (mocked install_family)
# ---------------------------------------------------------------------------


def _stub_install_family(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failed_tools: tuple[str, ...] = (),
):
    """Replace ``_orch.install_family`` with a recorder that mints a
    typed report based on the slice it received.

    Tools listed in ``failed_tools`` come back with ``state="failed"``
    so the per-tool failure-isolation contract can be exercised
    without having to wire up a real corrupt-SHA fixture.
    """
    captured: dict = {"calls": []}

    def _fake(manifest, *, project_root=None, on_event=None, **kwargs):
        captured["calls"].append(
            {
                "family_id": manifest.family_id,
                "project_root": project_root,
                "tools": tuple(t.tool for t in manifest.required),
            }
        )
        outcomes = []
        for tool in manifest.required:
            failed = tool.tool in failed_tools
            # Emit the same events the real walker would so the
            # auto-fixer's log_lines list captures the failure
            # description.  Without this the log stays empty even
            # though the report carries `state="failed"` rows.
            if on_event is not None:
                if failed:
                    on_event(
                        _orch.ToolFailed(
                            tool=tool.tool,
                            version=tool.version,
                            error_type="family-toolchain-installer-checksum",
                            message="checksum mismatch",
                        )
                    )
                else:
                    on_event(
                        _orch.ToolInstalled(
                            tool=tool.tool,
                            version=tool.version,
                            sha256="deadbeef" * 8,
                            store_path=(project_root or Path("/tmp")) / "store" / tool.tool,
                            bytes_downloaded=1024,
                            udev_rules_path=None,
                            skipped=False,
                        )
                    )
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
            host=replace(_orch._ts.host_triple()),
            outcomes=tuple(outcomes),
            total_bytes_downloaded=sum(o.bytes_downloaded for o in outcomes),
            lockfile_updated=any(not o.state == "failed" for o in outcomes) and project_root is not None,
            lockfile_path=(project_root / ".alloy" / "toolchain.lock") if project_root else None,
        )

    monkeypatch.setattr(_orch, "install_family", _fake)
    return captured


def test_auto_fix_dispatches_install_family_with_single_tool_slice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fixer slices the manifest down to the failing tool and
    dispatches that slice through ``install_family``."""
    _seed_chip_project(tmp_path, family="stm32g0")
    captured = _stub_install_family(monkeypatch)

    check = CheckResult(
        name="cmake",
        ok=False,
        severity="error",
        message="missing",
        source="xpack",
        auto_fix="alloy toolchain install --for stm32g0 cmake",
    )
    outcome = _auto_fix_install_toolchain_tool(
        check, _process.runner, project_root=tmp_path
    )
    assert outcome.ok is True
    assert len(captured["calls"]) == 1
    call = captured["calls"][0]
    assert call["family_id"] == "stm32g0"
    assert call["project_root"] == tmp_path
    assert call["tools"] == ("cmake",)


def test_auto_fix_returns_failure_when_orchestrator_reports_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Orchestrator failure → ``AutoFixOutcome.ok=False`` with the log
    mentioning the typed error_type."""
    _seed_chip_project(tmp_path, family="stm32g0")
    _stub_install_family(monkeypatch, failed_tools=("cmake",))

    check = CheckResult(
        name="cmake",
        ok=False,
        severity="error",
        message="missing",
        source="xpack",
        auto_fix="alloy toolchain install --for stm32g0 cmake",
    )
    outcome = _auto_fix_install_toolchain_tool(
        check, _process.runner, project_root=tmp_path
    )
    assert outcome.ok is False
    assert "cmake" in outcome.log
    assert "checksum" in outcome.log


# ---------------------------------------------------------------------------
# CLI integration: alloy doctor --fix
# ---------------------------------------------------------------------------


def test_doctor_fix_dispatches_orchestrator_for_missing_required_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: `alloy doctor --fix --for stm32g0` queues the
    orchestrator once per missing required non-vendor tool."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)
    captured = _stub_install_family(monkeypatch)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        _seed_chip_project(Path(cwd), family="stm32g0")
        result = runner.invoke(
            cli,
            ["doctor", "--fix", "--for", "stm32g0", "--project-dir", cwd, "--json"],
        )
    assert result.exit_code in (0, 1), result.output  # 1 if errors remain after fix
    # Every required stm32g0 tool that's both missing AND non-vendor.
    # The required tier is inherited from arm-cortex-m: arm-none-eabi-gcc,
    # cmake, ninja, probe-rs.  STM32CubeProgrammer is recommended +
    # vendor — must NOT be queued.
    invoked_tools = {tool for call in captured["calls"] for tool in call["tools"]}
    assert "arm-none-eabi-gcc" in invoked_tools
    assert "cmake" in invoked_tools
    assert "ninja" in invoked_tools
    assert "probe-rs" in invoked_tools
    assert "STM32CubeProgrammer" not in invoked_tools


def test_doctor_fix_per_tool_failure_does_not_abort_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When tool N's install fails, tools N+1 onwards are still
    attempted — Wave 3 atomicity is per-tool, not per-queue."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)
    captured = _stub_install_family(monkeypatch, failed_tools=("cmake",))

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        _seed_chip_project(Path(cwd), family="stm32g0")
        runner.invoke(
            cli,
            ["doctor", "--fix", "--for", "stm32g0", "--project-dir", cwd],
        )
    # All four required tools were attempted.
    invoked_tools = {tool for call in captured["calls"] for tool in call["tools"]}
    for tool in ("arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"):
        assert tool in invoked_tools, (
            f"`{tool}` queue entry must run even though `cmake` failed"
        )


def test_doctor_fix_default_excludes_recommended_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``--with-recommended`` the queue stops at the required
    tier — recommended tools surface in the report but are not
    auto-installed."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)
    captured = _stub_install_family(monkeypatch)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        _seed_chip_project(Path(cwd), family="stm32g0")
        runner.invoke(
            cli,
            ["doctor", "--fix", "--for", "stm32g0", "--project-dir", cwd],
        )
    invoked_tools = {tool for call in captured["calls"] for tool in call["tools"]}
    # `tio` is recommended for stm32g0 — without --with-recommended it's
    # NOT queued.
    assert "tio" not in invoked_tools


def test_doctor_fix_with_recommended_includes_recommended_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--with-recommended`` extends the queue to recommended tools."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)
    captured = _stub_install_family(monkeypatch)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        _seed_chip_project(Path(cwd), family="stm32g0")
        runner.invoke(
            cli,
            [
                "doctor",
                "--fix",
                "--with-recommended",
                "--for",
                "stm32g0",
                "--project-dir",
                cwd,
            ],
        )
    invoked_tools = {tool for call in captured["calls"] for tool in call["tools"]}
    assert "tio" in invoked_tools, (
        "tio is in stm32g0's recommended tier and `--with-recommended` "
        "must extend the queue to it"
    )


def test_doctor_fix_without_resolvable_family_runs_legacy_fixers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running `alloy doctor --fix` outside any project (no `--for`,
    no alloy.toml) keeps the pre-Wave-3 behaviour: the toolchain
    auto-installer is silent, but `alloy-devices-yml` and `mcp`
    still run."""
    captured = _stub_install_family(monkeypatch)

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        # No alloy.toml → no family resolves.
        result = runner.invoke(
            cli,
            ["doctor", "--fix", "--project-dir", cwd, "--json"],
        )
    payload = json.loads(result.output)
    # The orchestrator must NEVER be called when no family resolves.
    assert captured["calls"] == []
    # Schema preserved.
    assert payload["schema_version"] == "1.1"


def test_doctor_with_recommended_help_advertises_flag() -> None:
    """`--help` lists the new flag — easy way to verify the click
    surface compiled."""
    runner = CliRunner()
    result = runner.invoke(cli, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--with-recommended" in result.output
