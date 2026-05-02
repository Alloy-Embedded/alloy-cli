"""``DoctorScreen`` — interactive host-environment diagnostics.

Mounts a ``DataTable`` populated from :func:`core.diagnose.run`
and binds:

- ``r`` to a full re-run (refreshes every row with a fresh report).
- ``f`` to applying the highlighted row's auto-fix (when one is
  registered in :data:`core.diagnose.AUTO_FIXERS`).
- ``Enter`` to a per-row detail view in the footer panel.
- ``Esc`` closes the screen.

The screen is the TUI counterpart to ``alloy doctor``.  Both go
through :data:`core.process.runner`, so tests can swap a
:class:`FakeRunner` to exercise auto-fix flows without touching
real processes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.coordinate import Coordinate
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from alloy_cli.core import diagnose as _diagnose
from alloy_cli.core.diagnose import CheckResult, DiagnosticReport
from alloy_cli.core.process import CommandRunner
from alloy_cli.core.process import runner as _default_runner

DiagnoseRun = Callable[..., DiagnosticReport]

# Glyph + severity column titles match the Rich-table CLI output so
# the two surfaces feel like the same product.
_GLYPH_OK = "✓"
_GLYPH_FAIL = "✗"


def _row_for(check: CheckResult) -> tuple[str, str, str, str, str, str]:
    """Render one CheckResult as a 6-tuple matching the table columns."""
    glyph = _GLYPH_OK if check.ok else _GLYPH_FAIL
    fix_marker = "auto" if _diagnose.get_auto_fix(check) is not None else "—"
    return (
        glyph,
        check.name,
        check.severity,
        check.message,
        check.install_hint or "—",
        fix_marker,
    )


class DoctorScreen(Screen[None]):
    """Diagnostic screen with re-run + per-row auto-fix bindings."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Close"),
        Binding("r", "rerun", "Re-run"),
        Binding("f", "auto_fix", "Auto-fix"),
        Binding("enter", "show_detail", "Detail"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    DoctorScreen #doctor-root {
        padding: 0 1;
    }
    DoctorScreen DataTable {
        height: 1fr;
    }
    DoctorScreen #doctor-detail {
        height: auto;
        min-height: 4;
        padding: 0 1;
        border-top: solid $primary;
    }
    DoctorScreen #doctor-status {
        padding: 0 1;
    }
    """

    def __init__(
        self,
        *,
        project_dir: Path | None = None,
        runner: CommandRunner | None = None,
        diagnose_run: DiagnoseRun | None = None,
    ) -> None:
        super().__init__()
        self._project_dir = (project_dir or Path.cwd()).resolve()
        self._runner: CommandRunner = runner or _default_runner
        # ``diagnose_run`` is a test seam — pilot tests inject a stub so
        # they don't have to monkey-patch the toolchain detectors.
        self._diagnose_run = diagnose_run or _diagnose.run
        self._report: DiagnosticReport = self._diagnose_run(project_dir=self._project_dir)

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="doctor-root"):
            yield Static(
                "[bold]Doctor[/bold]  "
                "[dim]r re-run · f auto-fix · Enter detail · Esc close[/dim]",
                id="doctor-status",
            )
            table: DataTable[str] = DataTable(id="doctor-table", zebra_stripes=True)
            table.cursor_type = "row"
            yield table
            yield Static("", id="doctor-detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.add_columns("status", "name", "severity", "message", "hint", "fix")
        self._populate_rows()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _populate_rows(self) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        for check in self._report.checks:
            table.add_row(*_row_for(check), key=check.name)

    def _refresh_status(self) -> None:
        ok_count = sum(1 for c in self._report.checks if c.ok)
        total = len(self._report.checks)
        glyph = _GLYPH_OK if not self._report.has_errors else _GLYPH_FAIL
        self.query_one("#doctor-status", Static).update(
            f"[bold]Doctor[/bold]  {glyph} {ok_count}/{total} ok  "
            f"[dim]r re-run · f auto-fix · Enter detail · Esc close[/dim]"
        )

    def _highlighted_check(self) -> CheckResult | None:
        table = self.query_one("#doctor-table", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._report.checks):
            return None
        return self._report.checks[table.cursor_row]

    def _replace_check(self, original: CheckResult, replacement: CheckResult) -> None:
        """Swap one check in the cached report (in-place row update)."""
        new_checks = tuple(
            replacement if c is original else c for c in self._report.checks
        )
        self._report = DiagnosticReport(checks=new_checks)
        table = self.query_one("#doctor-table", DataTable)
        # Find the row index and rewrite cells.
        for idx, check in enumerate(self._report.checks):
            if check is replacement:
                row_values = _row_for(check)
                for col, value in enumerate(row_values):
                    table.update_cell_at(Coordinate(idx, col), value)
                break
        self._refresh_status()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_rerun(self) -> None:
        self._report = self._diagnose_run(project_dir=self._project_dir)
        self._populate_rows()
        self._refresh_status()
        self.notify("Doctor report refreshed.", severity="information")

    def action_auto_fix(self) -> None:
        check = self._highlighted_check()
        if check is None:
            return
        fixer = _diagnose.get_auto_fix(check)
        if fixer is None:
            self.notify(
                f"No auto-fix registered for {check.name!r}.", severity="warning"
            )
            return
        outcome = fixer(check, self._runner, self._project_dir)
        if outcome.ok:
            replacement = CheckResult(
                name=check.name,
                ok=True,
                severity="info",
                message=f"Auto-fix applied ({check.name}).",
                install_hint=check.install_hint,
                auto_fix=None,
            )
        else:
            tail = (outcome.log or "auto-fix failed").splitlines()[-1]
            replacement = CheckResult(
                name=check.name,
                ok=False,
                severity="error",
                message=f"Auto-fix failed: {tail}",
                install_hint=check.install_hint,
                auto_fix=check.auto_fix,
            )
        self._replace_check(check, replacement)
        self._show_detail(replacement, log_tail=outcome.log)

    def action_show_detail(self) -> None:
        check = self._highlighted_check()
        if check is None:
            return
        self._show_detail(check)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_detail(self, check: CheckResult, *, log_tail: str = "") -> None:
        detail = self.query_one("#doctor-detail", Static)
        bits: list[str] = [f"[bold]{check.name}[/bold]"]
        bits.append(f"severity: {check.severity}")
        bits.append(f"message: {check.message}")
        if check.install_hint:
            bits.append(f"hint: {check.install_hint}")
        if check.auto_fix:
            bits.append(f"auto-fix: {check.auto_fix}")
        if log_tail:
            bits.append(f"[dim]log:[/dim]\n{log_tail}")
        detail.update("\n".join(bits))


__all__ = ["DoctorScreen"]
