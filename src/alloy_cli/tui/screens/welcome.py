"""Welcome / Help screen — fallback target until Phase-3 dashboards land."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli import __version__
from alloy_cli.tui.registry import register_screen


class WelcomeScreen(Screen):
    """The default landing screen for ``alloy ui``.

    Subsequent OpenSpec proposals (`add-tui-dashboard-and-onboarding`,
    `add-tui-board-picker`, …) replace this with the real dashboard.
    """

    DEFAULT_CSS = """
    WelcomeScreen Vertical {
        padding: 1 2;
    }
    """

    BINDINGS = [("q", "app.quit_with_confirm", "Quit"), ("?", "help", "Help")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Static(f"[bold cyan]alloy {__version__}[/bold cyan] — terminal UI")
            yield Static("")
            yield Static(
                "Welcome.  Phase-3 screens land in subsequent proposals "
                "([magenta]add-tui-dashboard-and-onboarding[/magenta], "
                "[magenta]add-tui-board-picker[/magenta], …)."
            )
            yield Static("")
            yield Static("[bold]Global keys[/bold]")
            yield Static("  Ctrl+P  open command palette")
            yield Static("  ?       help overlay")
            yield Static("  q       quit")
        yield Footer()

    def action_help(self) -> None:
        # Hook for Phase-3 contextual help.  For now, the welcome
        # screen *is* the help — no-op so the binding is preserved.
        self.notify("Help: see docs/TUI_DESIGN.md.")


@register_screen("welcome", title="Welcome", description="Landing screen")
def make_welcome() -> Screen:
    return WelcomeScreen()


__all__ = ["WelcomeScreen", "make_welcome"]
