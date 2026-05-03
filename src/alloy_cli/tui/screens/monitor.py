"""``MonitorScreen`` — Wave-4 live UART / RTT viewer.

Textual screen that streams target output to a ``RichLog`` widget.
Reusable from ``alloy ui`` (command palette) and from
``commands/monitor.py``'s TTY path (when Wave-5 wires the
hand-off).

Worker thread runs :func:`alloy_cli.core.probe_orchestrator.
open_monitor`; events stream back via ``app.call_from_thread``
mirroring the Wave-3 ``OnboardingScreen`` pattern.

Bindings:
- ``Ctrl+]`` close (graceful disconnect; raises
  ``ProbeOperationCancelledError`` from the worker thread which the
  screen catches + dismisses cleanly).
- ``Ctrl+L`` clear the log buffer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, RichLog, Static

from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import (
    AlloyCliError,
    FamilyToolchainProbeError,
    ProbeOperationCancelledError,
)
from alloy_cli.core.probe_orchestrator import (
    MonitorBytes,
    MonitorClosed,
    MonitorEvent,
    MonitorOpened,
)
from alloy_cli.tui.registry import register_screen


@dataclass(frozen=True, slots=True)
class MonitorSummary:
    """Returned via :meth:`Screen.dismiss` after a clean close."""

    bytes_captured: int
    duration_ms: int
    last_line: str | None


class MonitorScreen(Screen[MonitorSummary | None]):
    """Live UART / RTT viewer.

    Dismisses with a :class:`MonitorSummary` on graceful close
    (Ctrl+] or backend-driven session end), or ``None`` when the
    user cancels before the session opens.
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+]", "close_session", "Close monitor"),
        Binding("ctrl+l", "clear_log", "Clear log"),
        Binding("escape", "close_session", "Close monitor"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    MonitorScreen Vertical {
        padding: 0 1;
    }
    MonitorScreen #monitor-banner {
        text-style: bold;
        color: $accent;
        padding: 0 0 1 0;
    }
    MonitorScreen #monitor-log {
        height: 1fr;
        border: round $primary;
    }
    """

    def __init__(
        self,
        *,
        port: Path | str,
        baud: int = 115200,
        mode: str = "raw",
        probe: _po.Probe | None = None,
        ansi: bool = False,
        project_root: Path | None = None,
    ) -> None:
        super().__init__()
        self._port = port
        self._baud = baud
        self._mode = mode
        self._probe = probe
        self._ansi = ansi
        self._project_root = project_root
        self._bytes_total = 0
        self._last_line: str | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Static(self._banner_text(), id="monitor-banner")
            yield RichLog(id="monitor-log", highlight=False, markup=False)
        yield Footer()

    def _banner_text(self) -> str:
        return (
            f"Monitoring [bold]{self._port}[/bold] @ [bold]{self._baud}[/bold] "
            f"(mode={self._mode}, [dim]Ctrl+] to close[/dim])"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        """Spawn the orchestrator on a worker thread once the screen is mounted."""
        if self._probe is None:
            self._probe = self._build_probe()
        if self._probe is None:
            return  # error already surfaced via _build_probe
        self.run_worker(
            self._monitor_worker,
            thread=True,
            exclusive=True,
            name="alloy_monitor_worker",
        )

    def _build_probe(self) -> _po.Probe | None:
        """Resolve a probe lazily — only when ``__init__`` didn't get one.

        For raw-UART monitor sessions the probe is a no-op identity
        (the backend reads only port/baud).  For RTT sessions the
        screen relies on the caller injecting a real probe.
        """
        if self._mode == "rtt":
            try:
                identity = _po.select_probe(project_root=self._project_root)
            except FamilyToolchainProbeError as exc:
                self.notify(f"{exc}", severity="error")
                self.dismiss(None)
                return None
        else:
            identity = _po.ProbeIdentity(
                vid="0000",
                pid="0000",
                serial="",
                kind="serial",
                vendor_only=False,
            )
        try:
            return _po.real_probe_for(identity, project_root=self._project_root)
        except AlloyCliError as exc:
            self.notify(f"{exc}", severity="error")
            self.dismiss(None)
            return None

    def _monitor_worker(self) -> None:
        """Run on the worker thread; bridge events back via ``call_from_thread``."""
        assert self._probe is not None
        try:
            _po.open_monitor(
                self._probe,
                port=Path(self._port) if isinstance(self._port, str) else self._port,
                baud=self._baud,
                mode=self._mode,
                on_event=self._on_event_from_thread,
            )
        except ProbeOperationCancelledError as exc:
            self.app.call_from_thread(
                self._handle_close,
                _summary_from(exc),
            )
            return
        except AlloyCliError as exc:
            self.app.call_from_thread(self._handle_error, str(exc))
            return
        # Backend returned without raising — finite session.
        self.app.call_from_thread(
            self._handle_close,
            MonitorSummary(
                bytes_captured=self._bytes_total,
                duration_ms=0,
                last_line=self._last_line,
            ),
        )

    # ------------------------------------------------------------------
    # Event bridge (UI thread)
    # ------------------------------------------------------------------

    def _on_event_from_thread(self, event: MonitorEvent) -> None:
        self.app.call_from_thread(self._on_event, event)

    def _on_event(self, event: MonitorEvent) -> None:
        if isinstance(event, MonitorOpened):
            self._update_banner()
            return
        if isinstance(event, MonitorBytes):
            decoded = event.chunk.decode("utf-8", errors="replace")
            if not self._ansi:
                import re

                decoded = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", decoded)
            self._bytes_total += len(event.chunk)
            self._append_to_log(decoded)
            if "\n" in decoded:
                self._last_line = (
                    decoded.rsplit("\n", 1)[0].rsplit("\n", 1)[-1].strip() or self._last_line
                )
            self._update_banner()
            return
        if isinstance(event, MonitorClosed):
            self._handle_close(
                MonitorSummary(
                    bytes_captured=event.bytes_captured,
                    duration_ms=event.duration_ms,
                    last_line=event.last_line,
                )
            )

    def _append_to_log(self, text: str) -> None:
        try:
            log = self.query_one("#monitor-log", RichLog)
        except NoMatches:  # pragma: no cover — only during teardown
            return
        log.write(text, expand=True)

    def _update_banner(self) -> None:
        try:
            banner = self.query_one("#monitor-banner", Static)
        except NoMatches:  # pragma: no cover — only during teardown
            return
        banner.update(f"{self._banner_text()}  [dim]({self._bytes_total} bytes)[/dim]")

    # ------------------------------------------------------------------
    # Bindings + close
    # ------------------------------------------------------------------

    def action_close_session(self) -> None:
        """Ctrl+] / Esc → dismiss with the running summary."""
        if self._closed:
            return
        self._closed = True
        self.dismiss(
            MonitorSummary(
                bytes_captured=self._bytes_total,
                duration_ms=0,
                last_line=self._last_line,
            )
        )

    def action_clear_log(self) -> None:
        try:
            log = self.query_one("#monitor-log", RichLog)
        except NoMatches:  # pragma: no cover
            return
        log.clear()

    def _handle_close(self, summary: MonitorSummary) -> None:
        if self._closed:
            return
        self._closed = True
        self.dismiss(summary)

    def _handle_error(self, message: str) -> None:
        if self._closed:
            return
        self._closed = True
        self.notify(message, severity="error")
        self.dismiss(None)


def _summary_from(exc: ProbeOperationCancelledError) -> MonitorSummary:
    """Project the typed cancellation into the screen's dismiss return."""
    return MonitorSummary(
        bytes_captured=exc.bytes_captured,
        duration_ms=exc.duration_ms,
        last_line=exc.last_line,
    )


@register_screen(
    "monitor",
    title="Monitor",
    description="Live UART / RTT viewer — Ctrl+] to disconnect.",
)
def make_monitor() -> Screen:
    """Default factory: Wave-4 reaches it via the command palette
    with no preconfigured port; the user provides one when invoking
    `alloy monitor` from the CLI.  In `alloy ui` the command palette
    pushes this screen with a synthetic port so the user can wire
    it via the Settings dialog (Wave-5)."""
    return MonitorScreen(port="<unset>", baud=115200, mode="raw")


__all__ = [
    "MonitorScreen",
    "MonitorSummary",
    "make_monitor",
]
