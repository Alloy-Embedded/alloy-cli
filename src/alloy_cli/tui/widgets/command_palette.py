"""``CommandPalette`` — Ctrl+P fuzzy search over registered screens."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListItem, ListView, Static

from alloy_cli.tui.registry import ScreenEntry, registry


def _match_score(query: str, candidate: str) -> int | None:
    """Cheap fuzzy score: 0 = exact prefix, 1 = startswith, 2 = substring."""
    if not query:
        return 9
    needle = query.lower()
    haystack = candidate.lower()
    if haystack.startswith(needle):
        return 0
    for token in haystack.split():
        if token.startswith(needle):
            return 1
    return 2 if needle in haystack else None


class CommandPalette(ModalScreen[ScreenEntry]):
    """Fuzzy-searchable list of registered screens.

    The result is the chosen :class:`ScreenEntry`; callers wire it
    up via ``self.app.push_screen(palette, callback=...)``.  Pressing
    ``Esc`` returns ``None``.
    """

    BINDINGS = [
        ("escape", "cancel", "Close"),
    ]

    DEFAULT_CSS = """
    CommandPalette {
        align: center middle;
    }
    #palette {
        width: 60%;
        height: auto;
        max-height: 70%;
        padding: 1 2;
    }
    """

    def __init__(self, *, on_select: Callable[[ScreenEntry], None] | None = None) -> None:
        super().__init__()
        self._on_select = on_select

    def compose(self) -> ComposeResult:
        with Vertical(id="palette"):
            yield Static("[bold]Command Palette[/bold] — type to search, Enter to open")
            yield Input(placeholder="Search screens / commands…", id="palette-query")
            yield ListView(id="palette-results")

    def on_mount(self) -> None:
        self._refresh("")
        self.query_one("#palette-query", Input).focus()

    def _refresh(self, query: str) -> None:
        results: list[tuple[int, ScreenEntry]] = []
        for entry in registry:
            score = _match_score(query, entry.title) or _match_score(query, entry.name)
            if score is None:
                score = _match_score(query, entry.description or "")
            if score is None:
                continue
            results.append((score, entry))
        results.sort(key=lambda pair: (pair[0], pair[1].title))
        view = self.query_one("#palette-results", ListView)
        view.clear()
        for _, entry in results:
            label = (
                f"{entry.title}  [dim]{entry.description}[/dim]"
                if entry.description
                else entry.title
            )
            view.append(ListItem(Static(label), id=f"palette-item-{entry.name}"))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "palette-query":
            self._refresh(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        prefix = "palette-item-"
        if not item_id.startswith(prefix):
            return
        name = item_id[len(prefix) :]
        entry = registry.get(name)
        if entry is None:
            return
        if self._on_select is not None:
            self._on_select(entry)
        self.dismiss(entry)

    def action_cancel(self) -> None:
        self.dismiss(None)


__all__ = ["CommandPalette"]
