"""CLI integration tests for ``alloy toolchain``.

Pinned scenarios from
``openspec/changes/add-toolchain-installer/specs/cli-surface/spec.md``:

  * ``alloy toolchain install --dry-run --for esp32`` writes nothing.
  * ``alloy toolchain list --json`` reports installed + missing.
  * ``alloy toolchain use <tool>@<version>`` updates the lockfile.
  * ``alloy toolchain prune --dry-run`` lists candidates without
    deleting; ``alloy toolchain prune`` actually deletes.
  * ``alloy toolchain shell --print-path`` augments PATH for the
    spawned subshell only (we test the printed PATH instead of
    exec'ing a shell).
  * Vendor tools render the explicit "skipped (vendor — install
    manually)" line.
  * Unknown ``--for`` exits 2 with the available list.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import lockfile_toolchain as _lf
from alloy_cli.core import tool_sources as _ts
from alloy_cli.core import toolchain_manager as _tm
from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets a fresh ``ALLOY_TOOLS_ROOT`` under tmp_path.

    Also widen the terminal so Rich doesn't truncate tool names in
    the rendered tables — CliRunner runs without a real TTY, where
    Rich defaults to 80 columns and chops anything wider.
    """
    root = tmp_path / "store"
    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(root))
    monkeypatch.setenv("COLUMNS", "240")
    return root


def _sha_of(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _make_tarball(
    tmp_path: Path,
    *,
    name: str = "fake.tar.gz",
    subdir: str = "fake-1.0",
    binary_rel: str = "bin/fake-gcc",
) -> Path:
    src_dir = tmp_path / "_src" / subdir
    bin_dir = src_dir / Path(binary_rel).parent
    bin_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / binary_rel).write_bytes(b"#!/bin/sh\necho fake\n")
    archive = tmp_path / name
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src_dir, arcname=subdir)
    return archive


# ---------------------------------------------------------------------------
# --for unknown family
# ---------------------------------------------------------------------------


def test_install_unknown_family_exits_with_known_list(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "install",
            "--for",
            "totally-not-a-family",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    output = result.output
    assert "totally-not-a-family" in output
    # Every shipped family appears in the available list
    for fid in ("arm-cortex-m", "esp32", "nrf52", "rp2040", "stm32f4", "stm32g0"):
        assert fid in output


# ---------------------------------------------------------------------------
# install --dry-run
# ---------------------------------------------------------------------------


def test_install_dry_run_writes_nothing(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "install",
            "--for",
            "esp32",
            "--dry-run",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output.lower() or "Total estimated" in result.output

    # Nothing in the store
    store = Path(os.environ["ALLOY_TOOLS_ROOT"])
    if store.exists():
        assert not (store / "store").is_dir() or not list((store / "store").iterdir())
    # No project lockfile written
    assert not (tmp_path / ".alloy" / _lf.LOCKFILE_NAME).exists()


def test_install_dry_run_for_stm32g0_lists_required_tools(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "install",
            "--for",
            "stm32g0",
            "--dry-run",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    # Required tools (inherited from arm-cortex-m + family-specific) appear
    for tool in ("arm-none-eabi-gcc", "cmake", "ninja", "probe-rs"):
        assert tool in result.output


def test_install_dry_run_renders_vendor_tools_as_skipped(tmp_path: Path) -> None:
    """STM32CubeProgrammer is `source: vendor` on stm32g0 — the dry-run
    plan must explicitly mark it as skipped.
    """
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "install",
            "--for",
            "stm32g0",
            "--dry-run",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert "STM32CubeProgrammer" in result.output
    assert "vendor" in result.output.lower()
    assert "skip" in result.output.lower()


# ---------------------------------------------------------------------------
# install --apply (real, with FakeDownloader)
# ---------------------------------------------------------------------------


def _stub_pin_loader(
    monkeypatch: pytest.MonkeyPatch, *, sha: str, archive_url: str
) -> None:
    """Replace `_load_pins("xpack")` with a single-tool fixture pin
    whose URL + SHA match our test tarball.

    We cover only `xpack` here because the toolchain install test is
    about CLI orchestration; per-adapter coverage lives in
    ``test_tool_sources.py``.
    """
    fixture_payload = {
        "schema_version": "1.0.0",
        "source": "xpack",
        "_pending_verification": True,
        "tools": [
            {
                "tool": "fake-gcc",
                "version": "1.0.0",
                "hosts": {
                    str(_ts.host_triple()): {
                        "url": archive_url,
                        "sha256": sha,
                        "archive_kind": "tar.gz",
                        "extract_to_subdir": "fake-1.0",
                        "binaries": ["bin/fake-gcc"],
                    }
                },
            }
        ],
    }
    _ts._load_pins.cache_clear()
    real_load = _ts._load_pins.__wrapped__  # type: ignore[attr-defined]

    def _patched(kind: str) -> dict[str, object]:
        if kind == "xpack":
            return fixture_payload
        return real_load(kind)

    monkeypatch.setattr(_ts, "_load_pins", _patched)


def _stub_family(
    monkeypatch: pytest.MonkeyPatch,
    *,
    family_id: str,
    tool_name: str = "fake-gcc",
) -> None:
    """Replace `load_family(family_id)` with a manifest declaring just
    one fake tool sourced from xpack."""
    from alloy_cli.core.toolchain_registry import (
        FamilyManifest,
        ToolRequirement,
    )

    fake_manifest = FamilyManifest(
        family_id=family_id,
        core="cortex-m4f",
        arch="armv7em",
        schema_version="1.0.0",
        required=(
            ToolRequirement(
                tool=tool_name,
                version=">=1",
                source="xpack",
                capabilities=("build",),
            ),
        ),
        recommended=(),
        optional=(),
    )

    def _fake_load(family_id_arg: str) -> FamilyManifest:
        if family_id_arg == family_id:
            return fake_manifest
        from alloy_cli.core import toolchain_registry as tcr_real

        return tcr_real.load_family.__wrapped__(family_id_arg)  # type: ignore[attr-defined]

    monkeypatch.setattr("alloy_cli.core.toolchain_registry.load_family", _fake_load)
    monkeypatch.setattr("alloy_cli.commands.toolchain._registry.load_family", _fake_load)


def test_install_apply_writes_lockfile_and_populates_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: dry-run-OFF install runs the FakeDownloader and
    produces a lockfile + store entry.
    """
    archive = _make_tarball(tmp_path)
    sha = _sha_of(archive.read_bytes())
    url = f"https://example.com/{archive.name}"

    _stub_pin_loader(monkeypatch, sha=sha, archive_url=url)
    _stub_family(monkeypatch, family_id="arm-cortex-m")

    fake_dl = FakeDownloader()
    fake_dl.expect(url, archive)
    restore = _ts.configure_downloader(fake_dl)

    project_dir = tmp_path / "myproj"
    project_dir.mkdir()

    runner = CliRunner()
    try:
        result = runner.invoke(
            cli,
            [
                "toolchain",
                "install",
                "--for",
                "arm-cortex-m",
                "--project-dir",
                str(project_dir),
            ],
        )
    finally:
        restore()

    assert result.exit_code == 0, result.output
    assert "Installed fake-gcc 1.0.0" in result.output

    # Lockfile updated
    lock_path = project_dir / ".alloy" / _lf.LOCKFILE_NAME
    assert lock_path.exists()
    lock = _lf.read(lock_path)
    assert "fake-gcc" in lock.tools
    assert lock.tools["fake-gcc"].version == "1.0.0"
    assert lock.tools["fake-gcc"].sha256 == sha

    # Store has the extraction
    assert _tm.find_installed("fake-gcc") is not None


def test_install_shared_does_not_write_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _make_tarball(tmp_path)
    sha = _sha_of(archive.read_bytes())
    url = f"https://example.com/{archive.name}"
    _stub_pin_loader(monkeypatch, sha=sha, archive_url=url)
    _stub_family(monkeypatch, family_id="arm-cortex-m")
    fake_dl = FakeDownloader()
    fake_dl.expect(url, archive)
    restore = _ts.configure_downloader(fake_dl)

    project_dir = tmp_path / "myproj"
    project_dir.mkdir()
    runner = CliRunner()
    try:
        result = runner.invoke(
            cli,
            [
                "toolchain",
                "install",
                "--for",
                "arm-cortex-m",
                "--shared",
                "--project-dir",
                str(project_dir),
            ],
        )
    finally:
        restore()

    assert result.exit_code == 0, result.output
    # No project lockfile
    assert not (project_dir / ".alloy" / _lf.LOCKFILE_NAME).exists()
    # But store has the entry
    assert _tm.find_installed("fake-gcc") is not None


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_json_reports_installed_and_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-install one tool via the manager; CLI list should mark it
    `installed` and the recommended STM32CubeProgrammer as `vendor`.
    """
    # Install fake-gcc-1.0 directly via the manager
    archive = _make_tarball(tmp_path)
    sha = _sha_of(archive.read_bytes())
    url = f"https://example.com/{archive.name}"
    artifact = SourceArtifact(
        tool="arm-none-eabi-gcc",  # match what stm32g0 needs
        version="14.2.1-1.1",
        source="xpack",
        url=url,
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir="fake-1.0",
        binaries=("bin/fake-gcc",),
    )
    fake_dl = FakeDownloader()
    fake_dl.expect(url, archive)
    _tm.install(artifact, downloader=fake_dl)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "list",
            "--for",
            "stm32g0",
            "--json",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family_id"] == "stm32g0"

    by_tool = {row["tool"]: row for row in payload["tools"]}

    # arm-none-eabi-gcc is installed (we just put it there)
    assert by_tool["arm-none-eabi-gcc"]["state"] == "installed"
    assert by_tool["arm-none-eabi-gcc"]["installed_version"] == "14.2.1-1.1"
    assert by_tool["arm-none-eabi-gcc"]["installed_path"]

    # cmake / ninja / probe-rs are missing
    assert by_tool["cmake"]["state"] == "missing"
    assert by_tool["probe-rs"]["state"] == "missing"

    # STM32CubeProgrammer is vendor
    assert by_tool["STM32CubeProgrammer"]["state"] == "vendor"


def test_list_filter_installed_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _make_tarball(tmp_path)
    sha = _sha_of(archive.read_bytes())
    url = f"https://example.com/{archive.name}"
    artifact = SourceArtifact(
        tool="arm-none-eabi-gcc",
        version="14.2.1-1.1",
        source="xpack",
        url=url,
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir="fake-1.0",
        binaries=("bin/fake-gcc",),
    )
    fake_dl = FakeDownloader()
    fake_dl.expect(url, archive)
    _tm.install(artifact, downloader=fake_dl)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "list",
            "--for",
            "stm32g0",
            "--installed",
            "--json",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    states = {row["state"] for row in payload["tools"]}
    assert states == {"installed"}


def test_list_installed_and_missing_are_mutually_exclusive(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "list",
            "--for",
            "stm32g0",
            "--installed",
            "--missing",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


# ---------------------------------------------------------------------------
# use
# ---------------------------------------------------------------------------


def test_use_pins_known_version_into_lockfile(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "use",
            "arm-none-eabi-gcc@14.2.1-1.1",
            "--project-dir",
            str(project_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    lock_path = project_dir / ".alloy" / _lf.LOCKFILE_NAME
    assert lock_path.exists()
    lock = _lf.read(lock_path)
    assert "arm-none-eabi-gcc" in lock.tools
    assert lock.tools["arm-none-eabi-gcc"].version == "14.2.1-1.1"


def test_use_unknown_version_lists_available(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "use",
            "arm-none-eabi-gcc@9.9.9",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "9.9.9" in result.output
    assert "Available" in result.output


def test_use_unknown_tool_lists_known(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "use",
            "definitely-not-a-tool@1.0",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "definitely-not-a-tool" in result.output


def test_use_rejects_missing_at_separator(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "use",
            "no-version-here",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "TOOL@VERSION" in result.output


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


def _install_fake(tmp_path: Path, *, tool: str, version: str) -> str:
    """Install a fake tool via the manager directly; returns its sha."""
    archive = _make_tarball(
        tmp_path, name=f"{tool}-{version}.tar.gz", subdir=f"{tool}-{version}"
    )
    sha = _sha_of(archive.read_bytes())
    url = f"https://example.com/{tool}-{version}.tar.gz"
    artifact = SourceArtifact(
        tool=tool,
        version=version,
        source="xpack",
        url=url,
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir=f"{tool}-{version}",
        binaries=("bin/fake-gcc",),
    )
    fake_dl = FakeDownloader()
    fake_dl.expect(url, archive)
    _tm.install(artifact, downloader=fake_dl)
    return sha


def test_prune_dry_run_lists_unreferenced(tmp_path: Path) -> None:
    _install_fake(tmp_path, tool="orphan-tool", version="1.0")

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "prune",
            "--dry-run",
            "--project-dir",
            str(project_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "orphan-tool" in result.output
    assert "would delete" in result.output.lower() or "dry-run" in result.output.lower()
    # Manager still has the entry
    assert _tm.find_installed("orphan-tool") is not None


def test_prune_actually_deletes(tmp_path: Path) -> None:
    _install_fake(tmp_path, tool="trash", version="1.0")
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "prune",
            "--project-dir",
            str(project_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Pruned" in result.output
    assert _tm.find_installed("trash") is None


def test_prune_keeps_pinned_tools(tmp_path: Path) -> None:
    sha = _install_fake(tmp_path, tool="kept-tool", version="1.2.3")

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    lock = _lf.empty()
    lock = _lf.add(lock, "kept-tool", "1.2.3", sha)
    _lf.write(project_dir / ".alloy" / _lf.LOCKFILE_NAME, lock)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "toolchain",
            "prune",
            "--project-dir",
            str(project_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    # Pinned tool stayed
    assert _tm.find_installed("kept-tool") is not None


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------


def test_shell_print_path_augments(tmp_path: Path) -> None:
    """--print-path returns the augmented PATH instead of spawning a shell."""
    sha = _install_fake(tmp_path, tool="some-cli", version="1.0")
    assert sha  # quiet unused

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["toolchain", "shell", "--print-path", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    new_path = result.output.strip()
    # Cached bin dir is at the front
    parts = new_path.split(os.pathsep)
    assert any(
        "by-name" in p or "/store/" in p for p in parts
    ), f"no cached bin dir in PATH: {new_path}"


def test_shell_no_install_errors_clearly(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["toolchain", "shell", "--print-path", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "No toolchain binaries installed" in result.output


# ---------------------------------------------------------------------------
# General help discoverability
# ---------------------------------------------------------------------------


def test_toolchain_group_help_lists_five_verbs() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["toolchain", "--help"])
    assert result.exit_code == 0
    for verb in ("install", "list", "prune", "shell", "use"):
        assert verb in result.output


def test_toolchain_install_help_explains_dry_run() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["toolchain", "install", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
    assert "--shared" in result.output
    assert "--for" in result.output
