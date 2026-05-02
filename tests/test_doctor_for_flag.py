"""CLI integration tests for ``alloy doctor --for <family>``.

Spec scenarios pinned here:

  * ``alloy doctor --for nonexistent`` exits non-zero with the
    available family ids in the message.
  * ``alloy doctor --for stm32g0 --json`` emits the per-family
    check list (no esp32 tools, no rp2040 tools).
  * The rendered table carries a ``source`` column populated for
    toolchain rows and ``-`` for non-toolchain rows.
  * Vendor-source rows never participate in ``--fix`` (no auto-fix
    is registered for them, by design — we cannot redistribute
    EULA-gated binaries).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core import process as _process
from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core.diagnose import CheckResult, get_auto_fix
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# --for unknown family
# ---------------------------------------------------------------------------


def test_doctor_for_unknown_family_exits_with_known_list(tmp_path: Path) -> None:
    """Spec scenario: unknown --for value SHALL exit non-zero with the
    available family ids in stderr.
    """
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["doctor", "--for", "totally-not-a-real-family", "--project-dir", str(tmp_path)],
    )
    assert result.exit_code != 0, "doctor must exit non-zero on bad --for"

    output = result.output
    assert "totally-not-a-real-family" in output
    # Every shipped family appears in the available list (in alphabetical
    # order — Click renders the BadParameter message verbatim).
    for fid in ("arm-cortex-m", "esp32", "nrf52", "rp2040", "stm32f4", "stm32g0"):
        assert fid in output, f"available list missing {fid!r}"


def test_doctor_for_validation_runs_before_diagnose(tmp_path: Path) -> None:
    """Bad --for must fail at parse time — no diagnose I/O."""
    runner = CliRunner()
    result = runner.invoke(
        cli, ["doctor", "--for", "nope", "--project-dir", str(tmp_path)]
    )
    # Click's BadParameter handler renders to stderr (mixed into result.output
    # via CliRunner) and exits 2.
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# --for known family + JSON output
# ---------------------------------------------------------------------------


def test_doctor_for_stm32g0_json_lists_only_stm32g0_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["doctor", "--for", "stm32g0", "--json", "--project-dir", str(tmp_path)],
    )
    # The doctor exits 1 because tools are missing (errors); the JSON
    # still lands on stdout.
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1.1"
    names = {check["name"] for check in payload["checks"]}
    # Family-specific tools present
    assert "STM32CubeProgrammer" in names
    assert "tio" in names
    # Cortex-M base tools present (inherited via extends)
    assert "arm-none-eabi-gcc" in names
    # Other-family tools absent
    assert "xtensa-esp-elf-gcc" not in names
    assert "esptool" not in names
    assert "picotool" not in names


def test_doctor_for_esp32_json_lists_espressif_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["doctor", "--for", "esp32", "--json", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code in (0, 1), result.output
    payload = json.loads(result.output)
    names = {check["name"] for check in payload["checks"]}
    assert "xtensa-esp-elf-gcc" in names
    assert "esptool" in names
    # No ARM cross-compiler — esp32 doesn't extend arm-cortex-m
    assert "arm-none-eabi-gcc" not in names
    assert "probe-rs" not in names


# ---------------------------------------------------------------------------
# Source column rendering
# ---------------------------------------------------------------------------


def test_doctor_table_renders_source_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["doctor", "--for", "stm32g0", "--project-dir", str(tmp_path)]
    )
    output = result.output

    # The header is in the rendered table
    assert "source" in output.lower(), "source column header missing from doctor table"
    # At least one of the manifest source strings shows up
    has_source_value = any(
        marker in output for marker in ("xpack", "system", "vendor", "github:", "probe-rs-installer")
    )
    assert has_source_value, "no recognisable source values rendered in the table"


def test_doctor_json_carries_source_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 1.1 JSON contract puts `source` on every check row."""
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["doctor", "--for", "stm32g0", "--json", "--project-dir", str(tmp_path)],
    )
    payload = json.loads(result.output)
    for entry in payload["checks"]:
        assert "source" in entry, f"missing source on {entry.get('name')!r}"


# ---------------------------------------------------------------------------
# Vendor rows ↔ --fix isolation
# ---------------------------------------------------------------------------


def test_vendor_check_has_no_auto_fix() -> None:
    """The contract `vendor source ⇒ no auto_fix string` is what makes
    `_run_fixes` skip them naturally.

    Verified directly against ``get_auto_fix`` so a future regression
    (someone adds an auto_fix to a vendor check by accident) lights up
    immediately.
    """
    cube = CheckResult(
        name="STM32CubeProgrammer",
        ok=False,
        severity="info",
        message="not on PATH",
        install_hint="https://www.st.com/...",
        source="vendor (EULA — install manually)",
        auto_fix=None,
    )
    assert get_auto_fix(cube) is None, "vendor checks must have no auto_fix"


def test_run_fixes_skips_vendor_rows_in_auto_fix_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: doctor --fix on a stm32g0 project must NOT attempt to
    install STM32CubeProgrammer (vendor) even though it is missing.
    """
    _stub_toolchains_missing(monkeypatch)
    _stub_shutil_which(monkeypatch)

    # Capture every command the runner is asked to execute so we can
    # assert no vendor URL ever lands in argv.
    invoked: list[tuple[str, ...]] = []

    class _RecordingRunner:
        def run(self, args, **_kwargs):  # type: ignore[no-untyped-def]
            invoked.append(tuple(args))
            return _process.CommandResult(
                args=tuple(args), returncode=0, stdout="", stderr=""
            )

    monkeypatch.setattr(_process, "runner", _RecordingRunner())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["doctor", "--fix", "--for", "stm32g0", "--project-dir", str(tmp_path)],
    )

    # The runner may still be invoked for `git submodule update --init`
    # and `pip install alloy-cli[mcp]` — those have auto-fixers.  None
    # of the recorded invocations should mention STM32CubeProgrammer or
    # any st.com URL, because that tool is vendor-source.
    flat = " ".join(" ".join(args) for args in invoked).lower()
    assert "stm32cubeprog" not in flat
    assert "st.com" not in flat

    # And the auto-fix summary in the output must not list the vendor row.
    assert "STM32CubeProgrammer" not in result.output or "auto" not in result.output.lower().split(
        "stm32cubeprogrammer", 1
    )[-1].splitlines()[0]
