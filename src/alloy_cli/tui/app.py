"""``TuiApp`` — the Textual app shell every TUI screen lives inside."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from alloy_cli.tui.registry import ScreenEntry, registry
from alloy_cli.tui.theme import theme_path
from alloy_cli.tui.widgets.command_palette import CommandPalette


class _UnsavedChangesScreen(Screen[bool]):
    """Confirmation modal raised by :meth:`TuiApp.action_quit_with_confirm`."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Close"),
    ]

    DEFAULT_CSS = """
    _UnsavedChangesScreen {
        align: center middle;
    }
    _UnsavedChangesScreen > Static {
        width: 50%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "Discard pending changes? [bold]Y[/bold] yes / [bold]N[/bold] no",
            id="confirm-quit",
        )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class TuiApp(App[None]):
    """Textual application root.

    Loads its TCSS from :func:`theme_path` so ``ALLOY_TUI_THEME``
    + ``NO_COLOR`` are honoured.  Owns the global keybindings the
    spec mandates (``Ctrl+P``, ``?``, ``q``).
    """

    BINDINGS = [
        Binding("ctrl+p", "command_palette", "Palette", show=True),
        Binding("question_mark", "help", "Help", show=False),
        Binding("?", "help", "Help", show=True),
        Binding("q", "quit_with_confirm", "Quit", show=True),
    ]

    CSS_PATH: list[str]

    def __init__(self, *, dirty_callback=None, initial_screen: Screen | None = None) -> None:
        path = theme_path()
        self.CSS_PATH = [str(path)] if path.exists() else []
        super().__init__()
        self._dirty_callback = dirty_callback or (lambda: False)
        self._initial_screen = initial_screen

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Footer()

    def on_mount(self) -> None:
        if self._initial_screen is not None:
            self.push_screen(self._initial_screen)
            return
        # Default landing: Welcome screen if registered, else a stub.
        entry = registry.get("welcome")
        if entry is not None:
            self.push_screen(entry.factory())
        else:
            self.push_screen(_FallbackScreen())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_command_palette(self) -> None:
        self.push_screen(CommandPalette(), self._on_palette_dismissed)

    def _on_palette_dismissed(self, entry: ScreenEntry | None) -> None:
        if entry is None:
            return
        try:
            screen = entry.factory()
        except Exception as exc:
            self.notify(f"Could not open {entry.name}: {exc}", severity="error")
            return
        self.push_screen(screen)

    def action_help(self) -> None:
        # Default: relay through the active screen's ``action_help`` if any;
        # otherwise drop a notification.  Phase-3 screens will register
        # contextual overlays.
        screen = self.screen
        helper = getattr(screen, "action_help", None)
        if callable(helper):
            helper()
            return
        self.notify("No contextual help on this screen yet.", severity="information")

    def action_quit_with_confirm(self) -> None:
        if not self._dirty_callback():
            self.exit()
            return
        self.push_screen(_UnsavedChangesScreen(), self._on_confirm_quit)

    def _on_confirm_quit(self, confirmed: bool | None) -> None:
        if confirmed:
            self.exit()


class _FallbackScreen(Screen):
    """Stub used when no welcome screen is registered (e.g. early tests)."""

    def compose(self) -> ComposeResult:
        yield Static("alloy TUI — no screens registered.")


__all__ = ["TuiApp"]
