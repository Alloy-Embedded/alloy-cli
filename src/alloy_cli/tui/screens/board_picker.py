"""``BoardPickerScreen`` — faceted browser over the SDK catalogue."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, ListItem, ListView, Static

from alloy_cli.core import boards as _boards
from alloy_cli.core import search as _search
from alloy_cli.core.boards import BoardSummary
from alloy_cli.tui.registry import register_screen


class BoardPickerScreen(Screen[BoardSummary | None]):
    """CubeMX-quality board picker — Screen 2 in ``docs/TUI_DESIGN.md``."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "choose", "Select", show=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("f2", "toggle_detail", "Detail", show=True),
        Binding("tab", "cycle_focus", "Cycle focus", show=False),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    BoardPickerScreen {
        layers: base detail;
    }
    BoardPickerScreen #picker-root {
        padding: 0 1;
    }
    BoardPickerScreen #picker-search {
        margin-bottom: 1;
    }
    BoardPickerScreen #picker-body {
        height: 1fr;
    }
    BoardPickerScreen #picker-list {
        width: 50%;
        border: round $primary;
    }
    BoardPickerScreen #picker-detail {
        width: 50%;
        padding: 0 1;
        border: round $accent;
    }
    BoardPickerScreen #picker-count {
        color: $accent;
    }
    BoardPickerScreen.-detail-fullscreen #picker-list {
        display: none;
    }
    BoardPickerScreen.-detail-fullscreen #picker-detail {
        width: 100%;
    }
    """

    def __init__(self, *, title: str = "Pick a board") -> None:
        super().__init__()
        self._title = title
        self._query: str = ""
        self._results: tuple[BoardSummary, ...] = ()
        self._selected: BoardSummary | None = None
        self._detail_fullscreen = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="picker-root"):
            yield Input(placeholder="Search boards (type / to focus)…", id="picker-search")
            yield Static("", id="picker-count")
            with Horizontal(id="picker-body"):
                yield ListView(id="picker-list")
                yield Static("", id="picker-detail")
        yield Footer()

    async def on_mount(self) -> None:
        await self._refresh_results("")
        self.query_one("#picker-search", Input).focus()

    # ------------------------------------------------------------------
    # Search + selection
    # ------------------------------------------------------------------

    async def _refresh_results(self, query: str) -> None:
        self._query = query
        catalog = _boards.load_catalog()
        list_view = self.query_one("#picker-list", ListView)
        await list_view.clear()
        if not catalog:
            self._results = ()
            self.query_one("#picker-count", Static).update(
                "[yellow]Catalogue is empty.  Set ALLOY_BOARDS_ROOT.[/yellow]"
            )
            self.query_one("#picker-detail", Static).update("")
            return

        self._results = _search.search_boards(query=query or None)
        for board in self._results:
            label = f"{board.board_id}  [dim]{board.mcu or board.device}[/dim]"
            await list_view.append(ListItem(Static(label), id=f"pick-{board.board_id}"))

        self.query_one("#picker-count", Static).update(
            f"showing {len(self._results)}/{len(catalog)}"
        )

        # Highlight the first result so the detail pane has something to show.
        if self._results:
            list_view.index = 0
            self._select_board(self._results[0])
        else:
            self._selected = None
            self.query_one("#picker-detail", Static).update(
                "[yellow]No matches.  Adjust your search.[/yellow]"
            )

    def _select_board(self, board: BoardSummary) -> None:
        self._selected = board
        self.query_one("#picker-detail", Static).update(_render_board_detail(board))

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "picker-search":
            await self._refresh_results(event.value)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if item is None or not item.id:
            return
        prefix = "pick-"
        if not item.id.startswith(prefix):
            return
        board_id = item.id[len(prefix) :]
        for board in self._results:
            if board.board_id == board_id:
                self._select_board(board)
                return

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.action_choose()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_focus_search(self) -> None:
        self.query_one("#picker-search", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_choose(self) -> None:
        self.dismiss(self._selected)

    def action_cycle_focus(self) -> None:
        self.focus_next()

    def action_toggle_detail(self) -> None:
        self._detail_fullscreen = not self._detail_fullscreen
        css_class = "-detail-fullscreen"
        if self._detail_fullscreen:
            self.add_class(css_class)
        else:
            self.remove_class(css_class)


def _render_board_detail(board: BoardSummary) -> str:
    lines = [
        f"[bold cyan]{board.board_id}[/bold cyan]",
        f"  vendor:        {board.vendor}",
        f"  family:        {board.family}",
        f"  device:        {board.device}",
        f"  mcu:           {board.mcu or '-'}",
        f"  core:          {board.core or '-'}",
        f"  flash:         {board.flash_size_bytes or '?'} B",
        f"  tier:          {board.tier}",
        f"  features:      {', '.join(board.has_features) or '-'}",
        f"  clocks:        {', '.join(board.clock_profiles) or '-'}",
    ]
    if board.summary:
        lines.append("")
        lines.append(board.summary)
    return "\n".join(lines)


@register_screen(
    "board-picker",
    title="Board Picker",
    description="Faceted browser over the SDK catalogue",
)
def make_board_picker() -> Screen:
    return BoardPickerScreen()


__all__ = ["BoardPickerScreen", "make_board_picker"]
