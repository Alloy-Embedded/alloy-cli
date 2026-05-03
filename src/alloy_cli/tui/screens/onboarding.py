"""``OnboardingScreen`` — Wave-3 install wizard (3-phase).

Promoted from the Wave-1 placeholder.  The screen walks the user
through:

1. **Family picker** — auto-completes when the project's
   ``alloy.toml`` resolves to a family alloy-cli ships a manifest
   for; otherwise renders a sortable list from
   :func:`alloy_cli.core.boards.load_catalog`.
2. **Plan review** — every required + recommended tool the family
   declares as a Textual ``DataTable``.  Vendor (EULA-gated) tools
   render dim with their install_doc URL.
3. **Live progress** — once Install is pressed, dispatches
   :func:`alloy_cli.core.toolchain_orchestrator.install_family` on
   a worker thread and updates per-tool rows from the typed event
   stream.

The screen NEVER imports ``toolchain_manager`` or ``tool_sources``
directly — every install path goes through the shared orchestrator
so the four user-facing surfaces (alloy new / alloy setup /
alloy doctor --fix / TUI Onboarding / MCP apply tool) walk the same
family the same way.

Cancellation at any phase dismisses with an
:class:`OnboardingCancelledError` carrying the partial outcomes,
which the spawning context maps to exit code 130.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static
from textual.widgets.data_table import CellDoesNotExist

from alloy_cli.core import boards as _boards
from alloy_cli.core import toolchain_orchestrator as _orch
from alloy_cli.core import toolchain_registry as _registry
from alloy_cli.core.errors import (
    AlloyCliError,
    BoardNotFoundError,
    FamilyToolchainError,
    OnboardingCancelledError,
)
from alloy_cli.core.project import PROJECT_FILE, read
from alloy_cli.core.toolchain_orchestrator import (
    InstallEvent,
    InstallOutcome,
    InstallPlanItem,
    InstallReport,
    ToolDownloaded,
    ToolFailed,
    ToolInstalled,
    ToolSkippedHostUnsupported,
    ToolSkippedVendor,
    ToolStarted,
)
from alloy_cli.core.toolchain_registry import FamilyManifest
from alloy_cli.tui.registry import register_screen

# ---------------------------------------------------------------------------
# Phases (closed enum the screen branches on)
# ---------------------------------------------------------------------------


class Phase(enum.Enum):
    """Lifecycle phases of the install wizard."""

    FAMILY_PICKER = "family-picker"
    PLAN_REVIEW = "plan-review"
    LIVE_PROGRESS = "live-progress"
    COMPLETION = "completion"


@dataclass(slots=True)
class _ToolRow:
    """In-screen state for one tool's progress row."""

    tool: str
    version: str
    source: str
    status: str = "pending"  # 'pending' | 'started' | 'downloaded' | 'installed' | 'failed' | 'skipped-vendor' | 'skipped-host'
    detail: str = ""


@dataclass(slots=True)
class _OnboardingState:
    """Aggregated per-step state."""

    project_root: Path
    manifest: FamilyManifest | None = None
    plan: list[InstallPlanItem] = field(default_factory=list)
    rows: dict[str, _ToolRow] = field(default_factory=dict)
    outcomes: list[InstallOutcome] = field(default_factory=list)
    report: InstallReport | None = None


# ---------------------------------------------------------------------------
# Family resolution
# ---------------------------------------------------------------------------


def _resolve_family_for_project(project_root: Path) -> FamilyManifest | None:
    """Best-effort: read alloy.toml at project_root and resolve."""
    toml = project_root / PROJECT_FILE
    if not toml.exists():
        return None
    try:
        config = read(toml)
        return _registry.resolve_for_project(config)
    except (AlloyCliError, FamilyToolchainError):
        return None


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class OnboardingScreen(Screen[InstallReport | None]):
    """Three-phase toolchain install wizard.

    The screen dismisses with the :class:`InstallReport` on a
    completed install, or ``None`` when the user cancels at any
    phase before pressing Install.  Cancelling DURING the install
    raises :class:`OnboardingCancelledError` from the spawning
    context (so the CLI maps it to exit 130).
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    OnboardingScreen Vertical {
        padding: 1 2;
    }
    OnboardingScreen .phase-banner {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }
    OnboardingScreen .actions {
        padding-top: 1;
    }
    OnboardingScreen .vendor-row {
        color: $text-muted;
    }
    OnboardingScreen .done-banner {
        text-style: bold;
        color: $success;
        padding: 1 0;
    }
    """

    def __init__(
        self,
        *,
        project_root: Path,
        manifest: FamilyManifest | None = None,
    ) -> None:
        super().__init__()
        self._state = _OnboardingState(
            project_root=project_root.resolve(),
            manifest=manifest,
        )
        # Auto-resolve when no explicit manifest was provided.
        if manifest is None:
            self._state.manifest = _resolve_family_for_project(self._state.project_root)
        self._phase: Phase = (
            Phase.PLAN_REVIEW if self._state.manifest is not None else Phase.FAMILY_PICKER
        )

    # ------------------------------------------------------------------
    # Phase routing
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="onboarding-body"):
            yield Static(self._phase_banner(), id="phase-banner", classes="phase-banner")
            yield from self._compose_phase()
        yield Footer()

    def _phase_banner(self) -> str:
        phase_titles = {
            Phase.FAMILY_PICKER: "Step 1/3 — Pick a board",
            Phase.PLAN_REVIEW: "Step 2/3 — Review the install plan",
            Phase.LIVE_PROGRESS: "Step 3/3 — Installing…",
            Phase.COMPLETION: "All set — toolchain ready",
        }
        return phase_titles[self._phase]

    def _compose_phase(self) -> ComposeResult:
        if self._phase == Phase.FAMILY_PICKER:
            yield from self._compose_family_picker()
        elif self._phase == Phase.PLAN_REVIEW:
            yield from self._compose_plan_review()
        elif self._phase == Phase.LIVE_PROGRESS:
            yield from self._compose_live_progress()
        elif self._phase == Phase.COMPLETION:
            yield from self._compose_completion()

    # ------------------------------------------------------------------
    # Phase 1: Family picker
    # ------------------------------------------------------------------

    def _compose_family_picker(self) -> ComposeResult:
        catalog = _boards.load_catalog()
        if not catalog:
            yield Static(
                "[red]No board catalogue available.[/red]  Set "
                "[bold]ALLOY_BOARDS_ROOT[/bold] or run [bold]alloy boards[/bold]."
            )
            yield Horizontal(
                Button("Cancel", id="cancel", variant="error"),
                classes="actions",
            )
            return
        table = DataTable(id="board-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("board", "family", "mcu", "tier")
        # Sort by tier then board id so the highest-priority board
        # is first.
        for summary in sorted(catalog, key=lambda s: (s.tier, s.board_id)):
            table.add_row(
                summary.board_id,
                summary.family,
                summary.mcu,
                str(summary.tier),
                key=summary.board_id,
            )
        yield table
        yield Horizontal(
            Button("Pick", id="pick-board", variant="success"),
            Button("Cancel", id="cancel", variant="error"),
            classes="actions",
        )

    # ------------------------------------------------------------------
    # Phase 2: Plan review
    # ------------------------------------------------------------------

    def _compose_plan_review(self) -> ComposeResult:
        manifest = self._state.manifest
        assert manifest is not None
        if not self._state.plan:
            try:
                plan, warnings = _orch.plan_install(manifest)
            except AlloyCliError as exc:
                yield Static(f"[red]Plan resolution failed:[/red] {exc}")
                yield Horizontal(
                    Button("Cancel", id="cancel", variant="error"),
                    classes="actions",
                )
                return
            self._state.plan = plan
            for warning in warnings:
                self.notify(warning, severity="warning")

        table = DataTable(id="plan-table", zebra_stripes=True)
        table.add_columns("tool", "tier", "version", "source", "status", "size", "url")
        for item in self._state.plan:
            row_key = item.tool.tool
            self._state.rows[row_key] = _ToolRow(
                tool=item.tool.tool,
                version=item.tool.version,
                source=item.tool.source,
                status="pending",
                detail=item.skip_reason,
            )
            if item.is_actionable and item.artifact is not None:
                size = (
                    f"{item.artifact.size_bytes // 1024} KiB"
                    if item.artifact.size_bytes
                    else "?"
                )
                table.add_row(
                    item.tool.tool,
                    item.tier,
                    item.artifact.version,
                    item.artifact.source,
                    "pending",
                    size,
                    item.artifact.url,
                    key=row_key,
                )
            else:
                table.add_row(
                    f"[dim]{item.tool.tool}[/dim]",
                    item.tier,
                    item.tool.version,
                    item.tool.source,
                    "[dim]skip[/dim]",
                    "-",
                    f"[dim]{item.install_doc_url or item.skip_reason}[/dim]",
                    key=row_key,
                )
        yield table
        yield Horizontal(
            Button("Install", id="install", variant="success"),
            Button("Cancel", id="cancel", variant="error"),
            classes="actions",
        )

    # ------------------------------------------------------------------
    # Phase 3: Live progress
    # ------------------------------------------------------------------

    def _compose_live_progress(self) -> ComposeResult:
        table = DataTable(id="progress-table", zebra_stripes=True)
        table.add_columns("tool", "version", "status", "detail")
        for row in self._state.rows.values():
            table.add_row(
                row.tool,
                row.version,
                self._render_status(row.status),
                row.detail,
                key=row.tool,
            )
        yield table
        yield Horizontal(
            Button("Cancel", id="cancel", variant="error"),
            classes="actions",
        )

    @staticmethod
    def _render_status(status: str) -> str:
        glyphs = {
            "pending": "[dim]…[/dim]",
            "started": "[cyan]→ downloading[/cyan]",
            "downloaded": "[cyan]↓ downloaded[/cyan]",
            "installed": "[green]✓ installed[/green]",
            "failed": "[red]✗ failed[/red]",
            "skipped-vendor": "[dim]· vendor[/dim]",
            "skipped-host": "[dim]· host[/dim]",
        }
        return glyphs.get(status, status)

    # ------------------------------------------------------------------
    # Phase 4: Completion
    # ------------------------------------------------------------------

    def _compose_completion(self) -> ComposeResult:
        report = self._state.report
        if report is None:
            yield Static("[red]No report available.[/red]")
            yield Horizontal(
                Button("Exit wizard", id="exit", variant="primary"),
                classes="actions",
            )
            return
        yield Static(
            f"[bold green]✓ Toolchain ready.[/bold green]  "
            f"{report.installed_count} tool(s), "
            f"{report.total_bytes_downloaded // 1024} KiB downloaded.",
            classes="done-banner",
        )
        if report.failed_count:
            yield Static(
                f"[red]✗ {report.failed_count} tool(s) failed[/red] — "
                "check the table above for details."
            )
        if report.lockfile_updated and report.lockfile_path is not None:
            yield Static(f"[green]✓ Updated[/green] [bold]{report.lockfile_path}[/bold]")
        yield Static(
            "\nNext steps:\n"
            "  [bold]alloy build[/bold]\n"
            "  [bold]alloy flash[/bold]\n"
            "  [bold]alloy ui[/bold]   [dim]# launch the dashboard[/dim]"
        )
        yield Horizontal(
            Button("Exit wizard", id="exit", variant="primary"),
            classes="actions",
        )

    # ------------------------------------------------------------------
    # Button + binding handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "cancel":
            self._handle_cancel()
        elif bid == "pick-board":
            self._handle_pick_board()
        elif bid == "install":
            self._handle_install()
        elif bid == "exit":
            self.dismiss(self._state.report)

    def _handle_cancel(self) -> None:
        if self._phase == Phase.LIVE_PROGRESS:
            # Mid-install cancel: surface partial outcomes via a typed
            # exception so the spawning context can map it to exit 130.
            raise OnboardingCancelledError(
                "User cancelled during the live install phase.",
                partial_outcomes=tuple(self._state.outcomes),
            )
        self.dismiss(None)

    def _handle_pick_board(self) -> None:
        try:
            table = self.query_one("#board-table", DataTable)
        except NoMatches:  # pragma: no cover — only when phase mismatches
            return
        if table.cursor_row < 0:
            self.notify("Pick a board first.", severity="warning")
            return
        row_key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key
        board_id = row_key.value if row_key is not None else None
        if not board_id:
            self.notify("Could not resolve the picked row.", severity="error")
            return
        try:
            board_manifest = _boards.lookup(board_id)
        except BoardNotFoundError as exc:
            self.notify(f"Board lookup failed: {exc}", severity="error")
            return
        if not board_manifest.family:
            self.notify(
                f"Board {board_id!r} has no family pinned.", severity="error"
            )
            return
        try:
            self._state.manifest = _registry.load_family(board_manifest.family)
        except FamilyToolchainError as exc:
            self.notify(f"Family load failed: {exc}", severity="error")
            return
        self._phase = Phase.PLAN_REVIEW
        self.refresh(recompose=True)
        self._update_banner()

    def _handle_install(self) -> None:
        if self._state.manifest is None:
            self.notify("No family resolved; cannot install.", severity="error")
            return
        self._phase = Phase.LIVE_PROGRESS
        self.refresh(recompose=True)
        self._update_banner()
        # Worker thread: run install_family and pump events back via
        # call_from_thread so the UI updates safely.
        self.run_worker(
            self._install_worker,
            thread=True,
            exclusive=True,
            name="install_family",
        )

    def _update_banner(self) -> None:
        try:
            banner = self.query_one("#phase-banner", Static)
        except NoMatches:  # pragma: no cover — banner may not exist mid-recompose
            return
        banner.update(self._phase_banner())

    # ------------------------------------------------------------------
    # Worker thread + event dispatch
    # ------------------------------------------------------------------

    def _install_worker(self) -> None:
        manifest = self._state.manifest
        assert manifest is not None
        try:
            report = _orch.install_family(
                manifest,
                project_root=self._state.project_root,
                on_event=self._on_event_from_thread,
            )
        except AlloyCliError as exc:
            self.app.call_from_thread(
                self._on_install_error,
                str(exc),
                getattr(exc, "error_type", "alloy-cli-error"),
            )
            return
        self.app.call_from_thread(self._on_install_done, report)

    def _on_event_from_thread(self, event: InstallEvent) -> None:
        """Bridge from the worker thread into the UI thread."""
        self.app.call_from_thread(self._on_event, event)

    def _on_event(self, event: InstallEvent) -> None:
        tool: str
        if isinstance(event, ToolStarted):
            tool = event.tool
            self._update_row(tool, "started", event.url)
        elif isinstance(event, ToolDownloaded):
            tool = event.tool
            self._update_row(
                tool, "downloaded", f"{event.bytes_downloaded // 1024} KiB"
            )
        elif isinstance(event, ToolInstalled):
            tool = event.tool
            self._update_row(
                tool,
                "installed",
                f"sha {event.sha256[:8]}…" if event.sha256 else "",
            )
            self._state.outcomes.append(
                InstallOutcome(
                    tool=event.tool,
                    version=event.version,
                    state="installed" if not event.skipped else "skipped-already-installed",
                    sha256=event.sha256,
                    store_path=event.store_path,
                    bytes_downloaded=event.bytes_downloaded,
                    udev_rules_path=event.udev_rules_path,
                )
            )
        elif isinstance(event, ToolFailed):
            tool = event.tool
            self._update_row(tool, "failed", f"{event.error_type}: {event.message}")
            self._state.outcomes.append(
                InstallOutcome(
                    tool=event.tool,
                    version=event.version,
                    state="failed",
                    error_type=event.error_type,
                    error_message=event.message,
                )
            )
        elif isinstance(event, ToolSkippedVendor):
            tool = event.tool
            self._update_row(
                tool, "skipped-vendor", event.install_doc_url or "(see manifest)"
            )
        elif isinstance(event, ToolSkippedHostUnsupported):
            tool = event.tool
            self._update_row(
                tool, "skipped-host", f"no pin for host {event.host}"
            )

    def _update_row(self, tool: str, status: str, detail: str) -> None:
        row = self._state.rows.get(tool)
        if row is None:
            return
        row.status = status
        row.detail = detail
        try:
            table = self.query_one("#progress-table", DataTable)
        except NoMatches:  # pragma: no cover — phase may have changed
            return
        try:
            table.update_cell(tool, "status", self._render_status(status))
            table.update_cell(tool, "detail", detail)
        except CellDoesNotExist:  # pragma: no cover — row may not exist yet
            pass

    def _on_install_done(self, report: InstallReport) -> None:
        self._state.report = report
        self._phase = Phase.COMPLETION
        self.refresh(recompose=True)
        self._update_banner()

    def _on_install_error(self, message: str, error_type: str) -> None:
        self.notify(f"{error_type}: {message}", severity="error")
        self._phase = Phase.COMPLETION
        self.refresh(recompose=True)
        self._update_banner()

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        self._handle_cancel()


@register_screen(
    "onboarding",
    title="Onboarding",
    description="Toolchain install wizard — family picker, plan review, live progress.",
)
def make_onboarding() -> Screen:
    return OnboardingScreen(project_root=Path.cwd())


__all__ = [
    "OnboardingScreen",
    "Phase",
    "make_onboarding",
]
