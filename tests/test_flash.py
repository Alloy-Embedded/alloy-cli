"""Tests for ``alloy_cli.core.flash``: probe enumeration + run."""

from __future__ import annotations

import json

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
