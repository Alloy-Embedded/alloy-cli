"""Tests for ``alloy_cli.core.flash``: probe enumeration + run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alloy_cli.core import flash as _flash
from alloy_cli.core.flash import MultipleProbesError, ProbeInfo, ProbeNotFoundError
from alloy_cli.core.process import FakeRunner
from alloy_cli.core.project import ChipRef, ProjectConfig, ProjectMeta


def _config(chip: str = "stm32g071rb") -> ProjectConfig:
    return ProjectConfig(
        schema_version="1.0.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device=chip),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )


# ---------------------------------------------------------------------------
# detect_probes
# ---------------------------------------------------------------------------


def test_detect_probes_parses_json_output() -> None:
    fake = FakeRunner()
    payload = json.dumps(
        [
            {
                "type": "stlink",
                "serial_number": "0671FF565053837567200342",
                "vendor_id": 0x0483,
                "product_id": 0x374B,
                "identifier": "ST-Link V2.1",
            }
        ]
    )
    fake.expect(["probe-rs", "list", "--output=json"], stdout=payload, returncode=0)
    probes = _flash.detect_probes(runner=fake)
    assert len(probes) == 1
    assert probes[0].kind == "stlink"
    assert probes[0].serial == "0671FF565053837567200342"
    assert probes[0].vendor_id == 0x0483


def test_detect_probes_falls_back_to_plain_output() -> None:
    fake = FakeRunner()
    fake.expect(["probe-rs", "list", "--output=json"], stdout="", returncode=2)
    plain = (
        "The following debug probes were found:\n"
        "[0]: STLink V2-1 -- 0483:374b (serial: 0671FF565053837567200342)\n"
    )
    fake.expect(["probe-rs", "list"], stdout=plain, returncode=0)
    probes = _flash.detect_probes(runner=fake)
    assert len(probes) == 1
    assert probes[0].kind == "stlink"


def test_detect_probes_returns_empty_when_no_probes() -> None:
    fake = FakeRunner()
    fake.expect(["probe-rs", "list", "--output=json"], stdout="[]", returncode=0)
    fake.expect(["probe-rs", "list"], stdout="", returncode=0)
    probes = _flash.detect_probes(runner=fake)
    assert probes == ()


# ---------------------------------------------------------------------------
# select_probe
# ---------------------------------------------------------------------------


def _stlink() -> ProbeInfo:
    return ProbeInfo(
        kind="stlink", serial="abc", vendor_id=0x0483, product_id=0x374B, label="ST-Link"
    )


def _jlink() -> ProbeInfo:
    return ProbeInfo(
        kind="jlink", serial="999", vendor_id=0x1366, product_id=0x0101, label="J-Link"
    )


def test_select_probe_auto_returns_only_probe() -> None:
    p = _flash.select_probe((_stlink(),), requested="auto")
    assert p.kind == "stlink"


def test_select_probe_auto_with_multiple_raises() -> None:
    with pytest.raises(MultipleProbesError, match="2 probes detected"):
        _flash.select_probe((_stlink(), _jlink()), requested="auto")


def test_select_probe_explicit_kind_picks_match() -> None:
    p = _flash.select_probe((_stlink(), _jlink()), requested="jlink")
    assert p.kind == "jlink"


def test_select_probe_no_match_raises() -> None:
    with pytest.raises(ProbeNotFoundError, match="No probe of kind"):
        _flash.select_probe((_stlink(),), requested="picoprobe")


def test_select_probe_empty_list_raises() -> None:
    with pytest.raises(ProbeNotFoundError, match="No debug probe"):
        _flash.select_probe((), requested="auto")


def test_select_probe_two_same_kind_raises_multi() -> None:
    a = ProbeInfo(kind="stlink", serial="a", vendor_id=None, product_id=None, label="ST-Link #1")
    b = ProbeInfo(kind="stlink", serial="b", vendor_id=None, product_id=None, label="ST-Link #2")
    with pytest.raises(MultipleProbesError, match="2 'stlink' probes"):
        _flash.select_probe((a, b), requested="stlink")


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def test_run_invokes_probe_rs_run_with_chip_and_serial(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    fake = FakeRunner()
    fake.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps(
            [
                {
                    "type": "stlink",
                    "serial_number": "abc",
                    "vendor_id": 0x0483,
                    "product_id": 0x374B,
                    "identifier": "ST-Link",
                }
            ]
        ),
        returncode=0,
    )
    fake.expect(["probe-rs", "run"], returncode=0, stdout="Erasing\nProgramming\nDone")

    result = _flash.run(
        elf=elf,
        config=_config(),
        require_toolchain=False,
        runner=fake,
    )
    assert result.ok
    run_call = next(c for c in fake.calls if c.args[:2] == ("probe-rs", "run"))
    assert "--chip" in run_call.args
    assert "stm32g071rb" in run_call.args
    assert "stlink:abc" in run_call.args
    assert any("--probe" == a for a in run_call.args)


def test_run_propagates_probe_rs_failure(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    fake = FakeRunner()
    fake.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps([{"type": "jlink", "serial_number": "X"}]),
        returncode=0,
    )
    fake.expect(["probe-rs", "run"], returncode=1, stdout="ERROR\n")
    result = _flash.run(
        elf=elf,
        config=_config(),
        require_toolchain=False,
        runner=fake,
    )
    assert not result.ok
    assert result.returncode == 1


def test_run_streams_progress_to_on_line(tmp_path) -> None:
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    fake = FakeRunner()
    fake.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps([{"type": "stlink", "serial_number": "S"}]),
        returncode=0,
    )
    fake.expect(["probe-rs", "run"], returncode=0, stdout="Erasing\nProgramming\nDone")
    seen: list[str] = []
    _flash.run(
        elf=elf,
        config=_config(),
        require_toolchain=False,
        runner=fake,
        on_line=seen.append,
    )
    assert seen[-1] == "Done"


# ---------------------------------------------------------------------------
# Probe info smoke
# ---------------------------------------------------------------------------


def test_probe_short_format_includes_kind_and_serial() -> None:
    p = _stlink()
    assert "stlink" in p.short
    assert "abc" in p.short


def test_probe_short_format_omits_serial_when_none() -> None:
    p = ProbeInfo(kind="stlink", serial=None, vendor_id=None, product_id=None, label="ST-Link")
    assert "sn=" not in p.short


# ---------------------------------------------------------------------------
# Wave 2: lockfile-aware probe-rs resolution
# ---------------------------------------------------------------------------


def _seed_store_with_probe_rs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str = "0.27.0",
) -> str:
    """Install a fake probe-rs into an isolated store; returns the sha."""
    import hashlib
    import tarfile

    from alloy_cli.core import toolchain_manager as _tm
    from alloy_cli.core.tool_sources import FakeDownloader, SourceArtifact

    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(tmp_path / "_store" / "tools"))

    src = tmp_path / "_pkg" / f"probe-rs-tools-{version}"
    src.mkdir(parents=True, exist_ok=True)
    (src / "probe-rs").write_text("#!/bin/sh\nfake\n", encoding="utf-8")
    archive = tmp_path / f"probe-rs-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(src, arcname=f"probe-rs-tools-{version}")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()

    artefact = SourceArtifact(
        tool="probe-rs",
        version=version,
        source="probe-rs",
        url=f"https://example.com/probe-rs-{version}.tar.gz",
        sha256=sha,
        archive_kind="tar.gz",
        extract_to_subdir=f"probe-rs-tools-{version}",
        binaries=("probe-rs",),
    )
    fake_dl = FakeDownloader()
    fake_dl.expect(artefact.url, archive)
    _tm.install(artefact, downloader=fake_dl)
    return sha


def _seed_lockfile_with_probe_rs(
    project_root: Path, *, sha256: str, version: str = "0.27.0"
) -> None:
    from alloy_cli.core import lockfile_toolchain as _lf

    lock = _lf.add(_lf.empty(), "probe-rs", version, sha256)
    _lf.write(project_root / ".alloy" / _lf.LOCKFILE_NAME, lock)


def test_run_with_pinned_probe_rs_uses_store_path(tmp_path, monkeypatch) -> None:
    """Lockfile pins probe-rs + store has it → spawned argv begins with
    the absolute store path (not the bare ``probe-rs``).
    """
    sha = _seed_store_with_probe_rs(tmp_path, monkeypatch)
    project = tmp_path / "proj"
    project.mkdir()
    _seed_lockfile_with_probe_rs(project, sha256=sha)

    elf = project / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    fake = FakeRunner()
    # Match the cached probe-rs path prefix; both 'list' and 'run' will
    # invoke it as argv[0] = "<absolute path to>/probe-rs".
    fake.default = type(
        "_R",
        (),
        {
            "args": (),
            "returncode": 0,
            "stdout": json.dumps(
                [{"type": "stlink", "serial_number": "S"}]
            ),
            "stderr": "",
            "ok": True,
        },
    )()

    _flash.run(
        elf=elf,
        config=_config(),
        require_toolchain=False,
        runner=fake,
        project_root=project,
    )

    # Some call's argv[0] must end with /probe-rs and live under /store/.
    cached_observed = any(
        c.args and "store" in c.args[0] and c.args[0].endswith("probe-rs")
        for c in fake.calls
    )
    assert cached_observed, (
        f"no cached probe-rs path in argv: {[c.args for c in fake.calls]}"
    )
    bare_observed = any(c.args and c.args[0] == "probe-rs" for c in fake.calls)
    assert not bare_observed, (
        "fell back to PATH-resolved 'probe-rs' despite lockfile pin"
    )


def test_run_without_lockfile_keeps_bare_probe_rs_command(tmp_path) -> None:
    """Regression guard: legacy projects keep the pre-Wave-2 invocation
    byte-identical (argv[0] == 'probe-rs').
    """
    project = tmp_path / "proj"
    project.mkdir()
    elf = project / "firmware.elf"
    elf.write_bytes(b"\x7fELF")

    fake = FakeRunner()
    fake.expect(
        ["probe-rs", "list", "--output=json"],
        stdout=json.dumps([{"type": "stlink", "serial_number": "S"}]),
        returncode=0,
    )
    fake.expect(["probe-rs", "run"], returncode=0, stdout="OK")

    _flash.run(
        elf=elf,
        config=_config(),
        require_toolchain=False,
        runner=fake,
        project_root=project,
    )
    # Every call uses the bare 'probe-rs' command
    assert all(c.args and c.args[0] == "probe-rs" for c in fake.calls)


def test_run_with_pinned_probe_rs_missing_from_store_raises(
    tmp_path, monkeypatch
) -> None:
    """Lockfile pins probe-rs but the store has nothing → typed
    version-mismatch error before any subprocess runs.
    """
    monkeypatch.setenv("ALLOY_TOOLS_ROOT", str(tmp_path / "_empty" / "tools"))
    project = tmp_path / "proj"
    project.mkdir()
    _seed_lockfile_with_probe_rs(project, sha256="0" * 64)

    elf = project / "firmware.elf"
    elf.write_bytes(b"\x7fELF")
    fake = FakeRunner()  # MUST NOT be invoked

    from alloy_cli.core.errors import (
        FamilyToolchainInstallerVersionMismatchError,
    )

    with pytest.raises(FamilyToolchainInstallerVersionMismatchError):
        _flash.run(
            elf=elf,
            config=_config(),
            require_toolchain=False,
            runner=fake,
            project_root=project,
        )
    assert fake.calls == []
