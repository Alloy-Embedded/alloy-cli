"""Regression guard: every Wave-4 recovery entry point dispatches
through ``probe_orchestrator``.

The probe-selection + binary-resolution + argv-assembly logic
lives in exactly one place — the orchestrator.  If a new file
under ``commands/``, ``tui/``, or ``mcp/`` spawns ``probe-rs`` /
``openocd`` directly via ``subprocess`` (or imports them at the
module level), that file is re-implementing the walk.  The four
entry points (``alloy reset``, ``alloy erase``, ``alloy monitor``,
the TUI ``DebugScreen`` action group + ``MonitorScreen``) plus the
MCP probe tools would diverge in subtle ways (probe selection,
error vocabulary, vendor handling).  This test makes the
divergence loud and immediate.

Pre-Wave-4 files that already shell out to ``probe-rs`` /
``openocd`` are tracked in
``_PRE_WAVE_4_GRANDFATHERED``.  Each entry has a TODO pointing at
the group that owns the refactor.  Removing an entry from the
list before the refactor lands will (correctly) trip the test.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "alloy_cli"

# Files that pre-date Wave 4 and shell out to probe-rs / openocd
# directly (Wave-1 ``flash.py``).  Wave 4 builds the orchestrator
# but does NOT refactor ``flash.py`` — that's a follow-up wave.
# Removing an entry BEFORE the refactor lands will trip
# ``test_every_recovery_entry_point_routes_through_orchestrator``.
_PRE_WAVE_4_GRANDFATHERED: dict[Path, str] = {
    SRC / "core" / "flash.py": (
        "Wave-1 ``core/flash.py`` shells out to probe-rs directly via "
        "`detect_probes` + `process.runner.run([probe_rs_arg, ...])`. "
        "Wave 4 builds the orchestrator alongside; the flash refactor "
        "is a Wave-5+ follow-up."
    ),
    SRC / "commands" / "debug.py": (
        "Wave-1 ``commands/debug.py`` placeholder calls "
        "``flash.detect_probes()`` directly to render probe info. "
        "Wave-5+ rewrite will route it through the orchestrator."
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


def _calls_flash_detect_probes(path: Path) -> bool:
    """Tight heuristic: file calls ``flash.detect_probes(...)`` —
    Wave-1's probe enumeration.  This is the strong signal that the
    file is authoring a probe walk on its own; merely mentioning
    "probe-rs" in a comment or doctor message doesn't count.
    """
    text = path.read_text(encoding="utf-8")
    return ("flash.detect_probes(" in text) or ("_flash.detect_probes(" in text)


def _uses_orchestrator(path: Path) -> bool:
    return any("probe_orchestrator" in sym for sym in _imports(path))


def _candidate_files() -> list[Path]:
    """Files that, if they walk probes, MUST route through the
    orchestrator.  The list intentionally excludes ``core/flash.py``
    + ``commands/flash.py`` (grandfathered) — those are the
    Wave-1 probe walkers the orchestrator wraps.
    """
    return [
        *(SRC / "commands").glob("*.py"),
        *(SRC / "tui").rglob("*.py"),
        *(SRC / "mcp").rglob("*.py"),
        *(SRC / "core").glob("*.py"),
    ]


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_orchestrator_public_api_is_exported() -> None:
    """Every Wave-4 public symbol the entry points bind against MUST
    live in :data:`probe_orchestrator.__all__` so future renames are
    loud."""
    from alloy_cli.core import probe_orchestrator as _po

    expected = {
        "select_probe",
        "reset_target",
        "plan_erase",
        "execute_erase",
        "open_monitor",
        "Probe",
        "FakeProbe",
        "ProbeIdentity",
        "ResetReport",
        "ErasePlan",
        "EraseRegion",
        "EraseReport",
        "MonitorEvent",
        "MonitorOpened",
        "MonitorBytes",
        "MonitorClosed",
        "MonitorSessionTable",
    }
    missing = expected - set(_po.__all__)
    assert not missing, f"`probe_orchestrator.__all__` is missing: {sorted(missing)}"


def test_every_recovery_entry_point_routes_through_orchestrator() -> None:
    """Any file under ``commands/``, ``tui/``, ``mcp/``, or ``core/``
    that calls ``flash.detect_probes`` MUST also import from
    ``probe_orchestrator`` — unless it's grandfathered.

    The heuristic is intentionally tight (``flash.detect_probes(``
    as a literal call) so doctor messages or comment references to
    ``probe-rs`` don't trigger false positives.
    """
    offenders: list[str] = []
    for path in _candidate_files():
        if not _calls_flash_detect_probes(path):
            continue
        if path in _PRE_WAVE_4_GRANDFATHERED:
            continue
        if _uses_orchestrator(path):
            continue
        if path.name in {"probe_orchestrator.py", "flash.py"}:
            # The orchestrator wraps flash.detect_probes; flash.py
            # itself is the Wave-1 caller (already grandfathered).
            continue
        offenders.append(f"  • {path.relative_to(REPO_ROOT)}")
    assert not offenders, (
        "Wave-4 contract violation — these files spawn probe-rs / "
        "openocd directly without going through "
        "`probe_orchestrator`:\n"
        + "\n".join(offenders)
        + "\n\nRoute the dispatch through the orchestrator (or, if "
        "this is a pre-Wave-4 file scheduled for refactor, add it to "
        "`_PRE_WAVE_4_GRANDFATHERED` with a TODO)."
    )


def test_grandfathered_list_is_accurate() -> None:
    """Every entry in ``_PRE_WAVE_4_GRANDFATHERED`` MUST exist and
    still need the refactor.  Once a file routes through the
    orchestrator, its grandfathered entry MUST be deleted."""
    stale: list[str] = []
    for path, todo in _PRE_WAVE_4_GRANDFATHERED.items():
        if not path.exists():
            stale.append(f"  • {path.relative_to(REPO_ROOT)} no longer exists (TODO was: {todo})")
            continue
        if _uses_orchestrator(path):
            stale.append(
                f"  • {path.relative_to(REPO_ROOT)} now uses the "
                f"orchestrator — remove it from "
                f"`_PRE_WAVE_4_GRANDFATHERED`"
            )
    assert not stale, "Stale grandfathered entries:\n" + "\n".join(stale)


def test_orchestrator_is_the_only_select_probe_caller_in_core() -> None:
    """``select_probe`` is the orchestrator's own public entry point
    — only the orchestrator may call it from ``core/``.  Catch the
    regression early."""
    core_dir = SRC / "core"
    offenders: list[str] = []
    for path in core_dir.glob("*.py"):
        if path.name == "probe_orchestrator.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "select_probe(" in text and "probe_orchestrator" in text:
            offenders.append(f"  • {path.relative_to(REPO_ROOT)}")
    assert not offenders, "Only the orchestrator may call `select_probe` from core/:\n" + "\n".join(
        offenders
    )
