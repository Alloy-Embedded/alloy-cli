"""Regression guard: every Wave-3 onboarding entry point dispatches
through ``toolchain_orchestrator.install_family``.

The tier walk + vendor short-circuit + lockfile update logic lives
in exactly one place — the orchestrator.  If a new file under
``commands/``, ``tui/``, or ``mcp/`` imports from ``toolchain_manager``
and calls ``install`` on it, that file is re-implementing the walk.
The four entry points (``alloy new``, ``alloy doctor --fix``,
``alloy setup``, the TUI ``OnboardingScreen``) plus the MCP
``toolchain_apply_install_plan`` tool would diverge in subtle ways
(vendor handling, lockfile ordering, host-skip semantics).  This test
makes the divergence loud and immediate.

Pre-Wave-3 files that still walk the family directly are tracked in
the ``_PRE_WAVE_3_GRANDFATHERED`` map.  Each entry has a TODO
pointing at the group that owns the refactor.  When that refactor
lands the entry MUST be removed (``test_grandfathered_list_is_accurate``
fails fast if a file in the list no longer needs to be there).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "alloy_cli"

# Files that pre-date Wave 3 and call ``toolchain_manager.install``
# directly today.  Each will be migrated to dispatch via
# ``install_family`` in a later Wave-3 group.  Removing an entry from
# this map BEFORE the refactor lands will (correctly) trip
# ``test_every_entry_point_routes_through_install_family``.  Removing
# an entry AFTER the refactor lands is required (the
# grandfathered-accuracy test below enforces it).
_PRE_WAVE_3_GRANDFATHERED: dict[Path, str] = {
    SRC / "commands" / "toolchain.py": (
        "`alloy toolchain install` shells out to "
        "`toolchain_manager.install` directly; will route through "
        "`install_family` once Wave 3 finishes wiring the entry "
        "points (Group 2-6 of add-onboarding-wizard)."
    ),
}


def _imports(path: Path) -> set[str]:
    """Return the dotted names imported by ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out.add(f"{node.module}.{alias.name}")
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out


def _calls_install_attr(path: Path) -> bool:
    """Return True if ``path`` calls ``<something>.install(...)``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "install":
                return True
    return False


def _walks_family(path: Path) -> bool:
    """Heuristic: file imports ``toolchain_manager`` *and* calls
    ``.install``.  Together those mean the file is authoring an
    install walk on a family — and Wave 3's contract is that such a
    walk lives in exactly one place (the orchestrator).
    """
    imports = _imports(path)
    if not any("toolchain_manager" in sym for sym in imports):
        return False
    return _calls_install_attr(path)


def _uses_orchestrator(path: Path) -> bool:
    """Return True if ``path`` imports anything from
    ``toolchain_orchestrator`` (i.e., is willing to delegate to the
    shared walk)."""
    return any("toolchain_orchestrator" in sym for sym in _imports(path))


def _candidate_files() -> list[Path]:
    return [
        *(SRC / "commands").glob("*.py"),
        *(SRC / "tui").rglob("*.py"),
        *(SRC / "mcp").rglob("*.py"),
    ]


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_install_family_is_publicly_exported() -> None:
    """``install_family`` is the public entry — it MUST live in
    ``alloy_cli.core.toolchain_orchestrator.__all__`` so downstream
    callers (commands, tui, mcp) and external consumers can rely on
    a stable name.
    """
    from alloy_cli.core import toolchain_orchestrator as _orch

    assert "install_family" in _orch.__all__, (
        "`install_family` must be exported from `alloy_cli.core.toolchain_orchestrator.__all__`"
    )


def test_install_event_union_is_publicly_exported() -> None:
    """The five public ``InstallEvent`` classes are the documented
    surface every entry point binds against.  Keeping them in
    ``__all__`` prevents accidental privatisation."""
    from alloy_cli.core import toolchain_orchestrator as _orch

    expected = {
        "ToolStarted",
        "ToolDownloaded",
        "ToolInstalled",
        "ToolFailed",
        "ToolSkippedVendor",
        "ToolSkippedHostUnsupported",
        "InstallEvent",
        "InstallOutcome",
        "InstallReport",
        "install_family",
    }
    missing = expected - set(_orch.__all__)
    assert not missing, f"`toolchain_orchestrator.__all__` is missing: {sorted(missing)}"


def test_every_entry_point_routes_through_install_family() -> None:
    """Any file under ``commands/``, ``tui/``, or ``mcp/`` that walks
    a family (imports ``toolchain_manager`` *and* calls ``.install``)
    MUST also import from ``toolchain_orchestrator``.  Files listed
    in ``_PRE_WAVE_3_GRANDFATHERED`` are exempted with a TODO.
    """
    offenders: list[str] = []
    for path in _candidate_files():
        if not _walks_family(path):
            continue
        if path in _PRE_WAVE_3_GRANDFATHERED:
            continue
        if _uses_orchestrator(path):
            continue
        offenders.append(f"  • {path.relative_to(REPO_ROOT)}")
    assert not offenders, (
        "Wave-3 contract violation — these files call "
        "`toolchain_manager.install` directly but do not import "
        "`toolchain_orchestrator.install_family`:\n"
        + "\n".join(offenders)
        + "\n\nRoute the install through `install_family` (or, if "
        "this is a pre-Wave-3 file scheduled for refactor, add it "
        "to `_PRE_WAVE_3_GRANDFATHERED` with a TODO)."
    )


def test_grandfathered_list_is_accurate() -> None:
    """Every entry in ``_PRE_WAVE_3_GRANDFATHERED`` MUST (a) exist and
    (b) still walk the family directly today.  Once a refactor routes
    the file through ``install_family``, its grandfathered entry MUST
    be deleted — leaving stale entries hides regressions."""
    stale: list[str] = []
    for path, todo in _PRE_WAVE_3_GRANDFATHERED.items():
        if not path.exists():
            stale.append(f"  • {path.relative_to(REPO_ROOT)} no longer exists (TODO was: {todo})")
            continue
        if not _walks_family(path):
            stale.append(
                f"  • {path.relative_to(REPO_ROOT)} no longer calls "
                f"`toolchain_manager.install` directly — remove it "
                f"from `_PRE_WAVE_3_GRANDFATHERED`"
            )
            continue
        if _uses_orchestrator(path):
            stale.append(
                f"  • {path.relative_to(REPO_ROOT)} now uses the "
                f"orchestrator — remove it from "
                f"`_PRE_WAVE_3_GRANDFATHERED`"
            )
    assert not stale, "Stale grandfathered entries:\n" + "\n".join(stale)


# ``core/`` modules allowed to call ``install_family`` directly.  These
# are dispatchers (they delegate to the orchestrator on behalf of an
# entry point), not re-implementations of the walk.  Adding a new
# entry here is OK as long as the file truly delegates (one call into
# ``install_family``, no duplication of tier walk / vendor
# short-circuit / lockfile logic).
_CORE_INSTALL_FAMILY_DELEGATORS: set[Path] = {
    SRC / "core" / "diagnose.py",  # `alloy doctor --fix` auto-installer
}


def test_orchestrator_is_the_only_install_family_caller_in_core() -> None:
    """``install_family`` is the orchestrator's own public entry point.

    The only other ``core/`` callers permitted are explicit *dispatchers*
    listed in :data:`_CORE_INSTALL_FAMILY_DELEGATORS` — modules whose
    job is to call the orchestrator on behalf of an entry point (e.g.
    ``diagnose.py`` for ``alloy doctor --fix``).  Any other ``core/``
    module that calls ``install_family`` is almost certainly
    re-implementing the walk and should be rejected.
    """
    core_dir = SRC / "core"
    offenders: list[str] = []
    for path in core_dir.glob("*.py"):
        if path.name == "toolchain_orchestrator.py":
            continue
        if path in _CORE_INSTALL_FAMILY_DELEGATORS:
            continue
        text = path.read_text(encoding="utf-8")
        if "install_family(" in text:
            offenders.append(f"  • {path.relative_to(REPO_ROOT)}")
    assert not offenders, (
        "Only the orchestrator + listed delegators may call "
        "`install_family`:\n" + "\n".join(offenders)
    )
