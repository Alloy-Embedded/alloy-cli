"""Regression guards on ``docs/RECOVERY.md`` + the Wave-4 addendum
to ``docs/QUICKSTART.md``.

Every Wave-4 ``error_type`` is namedropped; every recovery command
has a subsection; every cookbook anchor is linked.  The QUICKSTART
addendum mentions the three commands and links to ``RECOVERY.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_DOC = REPO_ROOT / "docs" / "RECOVERY.md"
QUICKSTART_DOC = REPO_ROOT / "docs" / "QUICKSTART.md"


def _doc_text() -> str:
    return RECOVERY_DOC.read_text(encoding="utf-8")


def _quickstart_text() -> str:
    return QUICKSTART_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# RECOVERY.md
# ---------------------------------------------------------------------------


def test_doc_exists() -> None:
    assert RECOVERY_DOC.exists(), (
        "docs/RECOVERY.md must exist (Wave 4 group 7)."
    )


def test_doc_names_every_recovery_error_type() -> None:
    """Spec scenario: every Wave-4 ``error_type`` is mentioned by
    name so contributors authoring new entry points know what to
    branch on."""
    text = _doc_text()
    expected_errors = (
        "family-toolchain-probe-not-found",
        "family-toolchain-probe-not-attached",
        "family-toolchain-probe-multiple-attached",
        "family-toolchain-probe-unauthorised",
        "family-toolchain-erase-aborted",
        "family-toolchain-erase-unsupported-region",
        "family-toolchain-erase-confirmation-required",
        "family-toolchain-erase-probe-failed",
        "probe-operation-cancelled",
    )
    for error_type in expected_errors:
        assert error_type in text, (
            f"docs/RECOVERY.md must namedrop the {error_type!r} error_type"
        )


def test_doc_has_subsection_per_command() -> None:
    """Spec scenario: each command gets its own subsection."""
    text = _doc_text()
    headings = re.findall(r"^###\s+(.+)$", text, re.MULTILINE)
    joined = " | ".join(headings).lower()
    for token in ("alloy reset", "alloy erase", "alloy monitor"):
        assert token.lower() in joined, (
            f"docs/RECOVERY.md is missing the `{token}` subsection"
        )


def test_doc_links_every_error_to_the_cookbook() -> None:
    """Each Wave-4 error_type SHOULD appear as a clickable cookbook
    anchor.  Pin the contract so the doc + cookbook stay in sync."""
    text = _doc_text()
    expected_errors = (
        "family-toolchain-probe-not-found",
        "family-toolchain-probe-not-attached",
        "family-toolchain-probe-multiple-attached",
        "family-toolchain-probe-unauthorised",
        "family-toolchain-erase-aborted",
        "family-toolchain-erase-unsupported-region",
        "family-toolchain-erase-confirmation-required",
        "family-toolchain-erase-probe-failed",
        "probe-operation-cancelled",
    )
    for error_type in expected_errors:
        anchor = f"ERROR_COOKBOOK.md#{error_type}"
        assert anchor in text, (
            f"docs/RECOVERY.md is missing cookbook anchor for {error_type!r}"
        )


def test_doc_documents_two_phase_mcp_pattern() -> None:
    """The doc must show preview-then-confirm for ``probe_erase``."""
    text = _doc_text()
    assert "probe_erase_plan" in text
    assert "probe_erase" in text
    assert "confirm=True" in text or "confirm=true" in text
    assert "two-phase" in text.lower() or "two phase" in text.lower()


def test_doc_documents_vendor_probe_contract() -> None:
    """Vendor-only probes never auto-driven; install_doc URL surfaces."""
    text = _doc_text()
    assert "vendor" in text.lower()
    assert "install_doc" in text.lower() or "vendor_tool" in text.lower()
    assert "never" in text.lower()


def test_doc_documents_cancellation_contract() -> None:
    """Ctrl+] / monitor timeout → ``probe-operation-cancelled``."""
    text = _doc_text()
    assert "Ctrl+]" in text
    assert "probe-operation-cancelled" in text


def test_doc_cross_links_to_waves_1_through_3() -> None:
    text = _doc_text()
    assert "TOOLCHAIN_REGISTRY.md" in text, "Wave-1 cross-link missing"
    assert "TOOLCHAIN_INSTALLER.md" in text, "Wave-2 cross-link missing"
    assert "TOOLCHAIN_ONBOARDING.md" in text, "Wave-3 cross-link missing"


def test_doc_lists_every_monitor_event_class() -> None:
    """The sealed ``MonitorEvent`` union surfaces in the orchestrator
    section.  Each event class is mentioned by name."""
    text = _doc_text()
    for event in ("MonitorOpened", "MonitorBytes", "MonitorClosed"):
        assert event in text


def test_doc_mentions_fake_probe_test_seam() -> None:
    """``FakeProbe`` is the entry-point contract for tests; the doc
    documents it so contributors know where to look."""
    text = _doc_text()
    assert "FakeProbe" in text


def test_doc_links_to_implementation_modules() -> None:
    text = _doc_text()
    expected_modules = (
        "core/probe_orchestrator.py",
        "core/errors.py",
        "commands/reset.py",
        "commands/erase.py",
        "commands/monitor.py",
        "tui/screens/monitor.py",
        "mcp/tools.py",
    )
    for mod in expected_modules:
        assert mod in text, (
            f"docs/RECOVERY.md must mention `{mod}` so contributors find the impl"
        )


# ---------------------------------------------------------------------------
# QUICKSTART addendum
# ---------------------------------------------------------------------------


def test_quickstart_mentions_recovery_commands() -> None:
    text = _quickstart_text()
    for cmd in ("alloy reset", "alloy monitor", "alloy erase"):
        assert cmd in text, f"QUICKSTART must mention `{cmd}`"


def test_quickstart_links_to_recovery_doc() -> None:
    text = _quickstart_text()
    assert "RECOVERY.md" in text


def test_quickstart_documents_ctrl_close_for_monitor() -> None:
    text = _quickstart_text()
    assert "Ctrl+]" in text
