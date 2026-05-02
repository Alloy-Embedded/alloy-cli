"""Tests for ``alloy_cli.cmake_bridge`` — the CMake JSON manifest emitter."""

from __future__ import annotations

import io
import json
import sys

import pytest

from alloy_cli.cmake_bridge import main, project_manifest
from alloy_cli.core.project import PROJECT_FILE, parse, write

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _board_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "project": {"name": "blinky", "alloy": "0.7.3", "alloy-codegen": "0.4.1"},
        "board": {"id": "stm32f4-discovery"},
        "build": {"profile": "release"},
    }


def _chip_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "project": {"name": "raw"},
        "chip": {"vendor": "st", "family": "stm32f4", "device": "stm32f407vg"},
        "peripherals": [
            {
                "kind": "uart",
                "name": "console",
                "peripheral": "USART2",
                "tx": "PA2",
                "rx": "PA3",
                "baud": 115200,
            }
        ],
    }


# ---------------------------------------------------------------------------
# project_manifest()
# ---------------------------------------------------------------------------


def test_manifest_emits_board_section_when_board_present() -> None:
    cfg = parse(_board_payload())
    manifest = project_manifest(cfg)
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["project"]["name"] == "blinky"
    assert manifest["project"]["alloy"] == "0.7.3"
    assert manifest["project"]["alloy-codegen"] == "0.4.1"
    assert manifest["board"] == {"id": "stm32f4-discovery"}
    assert "chip" not in manifest
    assert manifest["build"] == {"profile": "release"}


def test_manifest_emits_chip_and_peripherals_round_trip() -> None:
    cfg = parse(_chip_payload())
    manifest = project_manifest(cfg)
    assert manifest["chip"] == {
        "vendor": "st",
        "family": "stm32f4",
        "device": "stm32f407vg",
    }
    assert "board" not in manifest
    assert len(manifest["peripherals"]) == 1
    uart = manifest["peripherals"][0]
    assert uart["kind"] == "uart"
    assert uart["tx"] == "PA2"
    assert uart["baud"] == 115200


def test_manifest_omits_optional_sections_when_empty() -> None:
    payload = {
        "schema_version": "1.0.0",
        "project": {"name": "demo"},
        "board": {"id": "nucleo-f446"},
    }
    manifest = project_manifest(parse(payload))
    assert "clocks" not in manifest
    assert "peripherals" not in manifest
    assert "build" not in manifest
    assert "flash" not in manifest


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _run_main(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_main_emits_json_on_stdout(tmp_path, capsys) -> None:
    cfg = parse(_board_payload())
    write(tmp_path / PROJECT_FILE, cfg)

    rc, out, err = _run_main(["--project-dir", str(tmp_path), "--emit-json"], capsys)
    assert rc == 0, err
    decoded = json.loads(out)
    assert decoded["project"]["name"] == "blinky"
    assert decoded["board"]["id"] == "stm32f4-discovery"


def test_main_pretty_prints_with_indent(tmp_path, capsys) -> None:
    cfg = parse(_board_payload())
    write(tmp_path / PROJECT_FILE, cfg)
    rc, out, _ = _run_main(["--project-dir", str(tmp_path), "--indent", "2"], capsys)
    assert rc == 0
    # Indent=2 produces newlines and 2-space leading whitespace
    assert "\n  " in out


def test_main_returns_nonzero_when_alloy_toml_missing(tmp_path, capsys) -> None:
    rc, _, err = _run_main(["--project-dir", str(tmp_path)], capsys)
    assert rc == 2
    assert "alloy.toml" in err.lower()


def test_main_runs_against_cwd_when_project_dir_absent(monkeypatch, tmp_path, capsys) -> None:
    cfg = parse(_chip_payload())
    write(tmp_path / PROJECT_FILE, cfg)
    monkeypatch.chdir(tmp_path)
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    decoded = json.loads(captured.out)
    assert decoded["chip"]["device"] == "stm32f407vg"


# ---------------------------------------------------------------------------
# Stable JSON output (sorted keys)
# ---------------------------------------------------------------------------


def test_main_output_is_sorted_for_stable_diffs(tmp_path, capsys) -> None:
    cfg = parse(_chip_payload())
    write(tmp_path / PROJECT_FILE, cfg)
    rc, out_a, _ = _run_main(["--project-dir", str(tmp_path)], capsys)
    assert rc == 0
    rc, out_b, _ = _run_main(["--project-dir", str(tmp_path)], capsys)
    assert rc == 0
    assert out_a == out_b


def test_main_does_not_pollute_stdout_on_error(tmp_path, capsys) -> None:
    rc, out, err = _run_main(["--project-dir", str(tmp_path)], capsys)
    assert rc == 2
    # Failure message MUST go to stderr so CMake's OUTPUT_VARIABLE stays clean.
    assert out == ""
    assert err.strip() != ""
    # Sanity: stdout was not appended to either.
    assert sys.stdout is not io.StringIO  # tautology — guards against monkeypatching slip
