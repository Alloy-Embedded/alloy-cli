"""End-to-end tests for ``alloy reset`` (Wave 4 group 2).

Pinned scenarios (lifted from ``cli-surface/spec.md``):

- Single-attached fast path renders the success panel.
- No probe attached → exit non-zero with the typed surface +
  cookbook link.
- Multiple probes attached + no ``--probe`` → exit non-zero with
  the typed envelope listing every probe.
- Vendor-only probe → exit non-zero with vendor tool name +
  install doc URL.
- ``--probe vid:pid:serial`` selector wins over autodetect.
- ``--soft`` (default) vs ``--hard`` toggles the dispatched method.
- ``--halt-after-reset`` is forwarded to the orchestrator.
- ``--help`` advertises every flag.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import (
    FamilyToolchainProbeMultipleAttachedError,
    FamilyToolchainProbeNotAttachedError,
    FamilyToolchainProbeUnauthorisedError,
)
from alloy_cli.main import cli

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


def _stlink(serial: str = "AAA") -> _po.ProbeIdentity:
    return _po.ProbeIdentity(
        vid="0483",
        pid="374b",
        serial=serial,
        kind="stlink",
        vendor_only=False,
    )


def _stub_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    probes: tuple[_po.ProbeIdentity, ...] = (),
    select_error: Exception | None = None,
    reset_error: Exception | None = None,
) -> dict:
    """Replace ``select_probe`` + ``real_probe_for`` + ``reset_target`` with
    recorders driven from the test.

    Returns a captured-state dict so tests can assert which arguments
    flowed through.  When ``probes`` is non-empty, ``select_probe`` is
    untouched (it sees the explicit tuple).  When ``select_error`` is
    set, ``select_probe`` raises it.
    """
    captured: dict = {
        "select_calls": [],
        "real_probe_calls": [],
        "reset_calls": [],
    }

    if select_error is not None:

        def _fake_select_raises(*, hint=None, project_root=None, probes=None):
            captured["select_calls"].append({"hint": hint, "project_root": project_root})
            raise select_error

        monkeypatch.setattr(_po, "select_probe", _fake_select_raises)
    else:
        # Wrap the real select_probe so we can record its arguments
        # while still using its full selection logic (vendor-only check,
        # multiple-attached error, hint matching).  Inject the explicit
        # ``probes`` tuple by patching ``_list_probes``.
        original_select = _po.select_probe

        def _fake_select_records(*, hint=None, project_root=None, probes=None):
            captured["select_calls"].append({"hint": hint, "project_root": project_root})
            return original_select(hint=hint, project_root=project_root, probes=probes)

        monkeypatch.setattr(_po, "select_probe", _fake_select_records)
        monkeypatch.setattr(_po, "_list_probes", lambda *, project_root=None: probes)

    fake_probe = _po.FakeProbe(identity=probes[0] if probes else _stlink())

    def _fake_real_probe_for(identity, *, project_root=None, runner=None):
        captured["real_probe_calls"].append({"identity": identity, "project_root": project_root})
        return fake_probe

    monkeypatch.setattr(_po, "real_probe_for", _fake_real_probe_for)

    if reset_error is not None:
        fake_probe.fail_next_reset(reset_error)

    captured["fake_probe"] = fake_probe
    return captured


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


def test_reset_help_lists_every_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["reset", "--help"])
    assert result.exit_code == 0
    for flag in ("--soft", "--hard", "--halt-after-reset", "--probe", "--project-dir"):
        assert flag in result.output


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_reset_single_attached_renders_success_panel(tmp_path, monkeypatch) -> None:
    """One attached probe → soft reset; success panel mentions probe + duration."""
    captured = _stub_orchestrator(monkeypatch, probes=(_stlink(),))
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert "Target reset" in result.output
    assert "stlink" in result.output
    assert "soft" in result.output
    assert len(captured["fake_probe"].reset_calls) == 1
    call = captured["fake_probe"].reset_calls[0]
    assert call.method == "soft"
    assert call.halt_after is False


def test_reset_hard_dispatches_hard_method(tmp_path, monkeypatch) -> None:
    captured = _stub_orchestrator(monkeypatch, probes=(_stlink(),))
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--hard", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    call = captured["fake_probe"].reset_calls[0]
    assert call.method == "hard"


def test_reset_halt_after_reset_is_forwarded(tmp_path, monkeypatch) -> None:
    captured = _stub_orchestrator(monkeypatch, probes=(_stlink(),))
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--halt-after-reset", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    call = captured["fake_probe"].reset_calls[0]
    assert call.halt_after is True
    assert "halted after reset" in result.output


def test_reset_probe_selector_disambiguates(tmp_path, monkeypatch) -> None:
    """``--probe 0483:374b:AAA`` picks AAA out of two attached probes."""
    aaa = _stlink("AAA")
    bbb = _stlink("BBB")
    captured = _stub_orchestrator(monkeypatch, probes=(aaa, bbb))
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--probe", "0483:374b:AAA", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    # The select_probe call carried the hint.
    assert captured["select_calls"][0]["hint"] == "0483:374b:AAA"


# ---------------------------------------------------------------------------
# Typed error paths
# ---------------------------------------------------------------------------


def test_reset_no_probe_attached_exits_non_zero(tmp_path, monkeypatch) -> None:
    err = FamilyToolchainProbeNotAttachedError("No probe attached.")
    _stub_orchestrator(monkeypatch, select_error=err)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--project-dir", cwd])
    assert result.exit_code != 0
    assert "No probe attached" in result.output
    assert "family-toolchain-probe-not-attached" in result.output


def test_reset_multiple_probes_lists_them(tmp_path, monkeypatch) -> None:
    err = FamilyToolchainProbeMultipleAttachedError(
        detected=(
            ("0483", "374b", "AAA", "stlink"),
            ("0483", "374b", "BBB", "stlink"),
        ),
    )
    _stub_orchestrator(monkeypatch, select_error=err)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--project-dir", cwd])
    assert result.exit_code != 0
    assert "stlink 0483:374b:AAA" in result.output
    assert "stlink 0483:374b:BBB" in result.output
    assert "family-toolchain-probe-multiple-attached" in result.output


def test_reset_vendor_only_probe_names_vendor_tool(tmp_path, monkeypatch) -> None:
    err = FamilyToolchainProbeUnauthorisedError(
        vendor_tool="J-Link Commander",
        install_doc_url="https://www.segger.com/downloads/jlink/",
    )
    _stub_orchestrator(monkeypatch, select_error=err)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--project-dir", cwd])
    assert result.exit_code != 0
    assert "J-Link Commander" in result.output
    assert "segger.com" in result.output
    assert "family-toolchain-probe-unauthorised" in result.output


def test_reset_orchestrator_call_carries_project_dir(tmp_path, monkeypatch) -> None:
    """The orchestrator sees the resolved ``--project-dir`` so the
    lockfile-pinned probe-rs binary resolution lands in the right place."""
    captured = _stub_orchestrator(monkeypatch, probes=(_stlink(),))
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        result = runner.invoke(cli, ["reset", "--project-dir", cwd])
    assert result.exit_code == 0, result.output
    assert captured["select_calls"][0]["project_root"].name == cwd.split("/")[-1]
    assert captured["real_probe_calls"][0]["project_root"].name == cwd.split("/")[-1]
