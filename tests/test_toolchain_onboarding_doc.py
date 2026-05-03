"""Regression guards on ``docs/TOOLCHAIN_ONBOARDING.md`` + the
Wave-3 rewrite of ``docs/QUICKSTART.md``.

The doc is the contributor + user-facing reference for the four
entry points + the shared orchestrator API + the two-phase MCP
pattern.  Every event class, every entry point, every cookbook
anchor mentioned in the spec scenario must be present in the doc
or these tests fail loudly.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ONBOARDING_DOC = REPO_ROOT / "docs" / "TOOLCHAIN_ONBOARDING.md"
QUICKSTART_DOC = REPO_ROOT / "docs" / "QUICKSTART.md"


def _doc_text() -> str:
    return ONBOARDING_DOC.read_text(encoding="utf-8")


def _quickstart_text() -> str:
    return QUICKSTART_DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# TOOLCHAIN_ONBOARDING.md
# ---------------------------------------------------------------------------


def test_doc_exists() -> None:
    assert ONBOARDING_DOC.exists(), (
        "docs/TOOLCHAIN_ONBOARDING.md must exist (Wave 3 group 7)."
    )


def test_doc_names_every_install_event_class() -> None:
    """Spec scenario: every event class name is mentioned by name so
    contributors authoring new entry points know what to subscribe to."""
    text = _doc_text()
    expected_events = (
        "ToolStarted",
        "ToolDownloaded",
        "ToolInstalled",
        "ToolFailed",
        "ToolSkippedVendor",
        "ToolSkippedHostUnsupported",
    )
    for event in expected_events:
        assert event in text, (
            f"docs/TOOLCHAIN_ONBOARDING.md must namedrop the "
            f"`{event}` event class"
        )


def test_doc_lists_every_entry_point_subsection() -> None:
    """Spec scenario: each entry point gets its own subsection."""
    text = _doc_text()
    # Use ###-level headings (subsections under "The four entry
    # points") so the regex stays narrow.
    headings = re.findall(r"^###\s+(.+)$", text, re.MULTILINE)
    joined_headings = " | ".join(headings).lower()
    for token in (
        "alloy new",
        "alloy doctor",
        "alloy setup",
        "onboardingscreen",
        "toolchain_apply_install_plan",
    ):
        assert token.lower() in joined_headings, (
            f"docs/TOOLCHAIN_ONBOARDING.md is missing the `{token}` "
            f"subsection"
        )


def test_doc_documents_cancellation_contract() -> None:
    """Spec scenario: the ``onboarding-cancelled`` anchor is linked
    so the cookbook stays cross-referenced."""
    text = _doc_text()
    assert "onboarding-cancelled" in text
    assert "ERROR_COOKBOOK.md#onboarding-cancelled" in text


def test_doc_cross_links_to_wave1_and_wave2() -> None:
    text = _doc_text()
    assert "TOOLCHAIN_REGISTRY.md" in text, "Wave 1 cross-link missing"
    assert "TOOLCHAIN_INSTALLER.md" in text, "Wave 2 cross-link missing"


def test_doc_documents_two_phase_mcp_pattern() -> None:
    """The doc must show the read-then-apply pattern explicitly so
    contributors authoring new MCP integrations don't skip the
    preview step."""
    text = _doc_text()
    assert "toolchain_install_plan" in text
    assert "toolchain_apply_install_plan" in text
    assert "two-phase" in text.lower() or "two phase" in text.lower()


def test_doc_documents_vendor_short_circuit() -> None:
    """Vendor tools NEVER auto-install — the doc must say so."""
    text = _doc_text()
    assert "vendor" in text.lower()
    assert "install_doc" in text.lower()
    assert "never" in text.lower()


def test_doc_lists_every_outcome_state() -> None:
    """Every closed-enum value in ``InstallOutcome.state`` appears in
    the doc — agents use these as branch keys."""
    text = _doc_text()
    expected_states = (
        "installed",
        "skipped-already-installed",
        "skipped-vendor",
        "skipped-host-unsupported",
        "failed",
    )
    for state in expected_states:
        assert state in text, f"state value `{state}` missing from doc"


def test_doc_links_to_implementation_modules() -> None:
    text = _doc_text()
    expected_modules = (
        "core/toolchain_orchestrator.py",
        "commands/_install_view.py",
        "commands/new.py",
        "commands/doctor.py",
        "commands/setup.py",
        "tui/screens/onboarding.py",
        "mcp/tools.py",
    )
    for mod in expected_modules:
        assert mod in text, (
            f"docs/TOOLCHAIN_ONBOARDING.md must mention `{mod}` so "
            f"contributors find the impl"
        )


# ---------------------------------------------------------------------------
# QUICKSTART.md (Wave-3 rewrite)
# ---------------------------------------------------------------------------


def test_quickstart_references_install_toolchain_flow() -> None:
    """Spec scenario: the rewritten QUICKSTART references the
    post-scaffold install path, not the explicit
    ``alloy toolchain install`` step."""
    text = _quickstart_text()
    # Either the flag OR the prompt language survives.
    assert (
        "--install-toolchain" in text
        or "Install toolchain now?" in text
        or "answer Y" in text.lower()
    )


def test_quickstart_includes_alloy_doctor_fix_for_existing_projects() -> None:
    text = _quickstart_text()
    assert "alloy doctor --fix" in text, (
        "QUICKSTART must point users at `alloy doctor --fix` for the "
        "'cloned an existing project' path"
    )


def test_quickstart_links_to_toolchain_onboarding() -> None:
    text = _quickstart_text()
    assert "TOOLCHAIN_ONBOARDING.md" in text


def test_quickstart_mentions_no_install_toolchain_escape_hatch() -> None:
    """Users with externally-managed toolchains need the escape
    hatch documented."""
    text = _quickstart_text()
    assert "--no-install-toolchain" in text


def test_quickstart_mentions_vendor_skip_for_stm32() -> None:
    """The 290-MB / vendor-tool reality check must be in the doc."""
    text = _quickstart_text()
    assert "STM32CubeProgrammer" in text or "vendor" in text.lower()
