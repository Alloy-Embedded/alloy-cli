"""``DiffWidget`` + ``DiffModal`` — unified-diff viewer + apply gate."""

from __future__ import annotations

from collections.abc import Callable

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from alloy_cli.core.diagnostics import UnifiedDiff


class DiffWidget(Static):
    """Renders a :class:`UnifiedDiff` with syntax highlighting.

    Use ``DiffWidget(diff)`` directly for inline rendering or
    :class:`DiffModal` for the apply-gate modal.
    """

    DEFAULT_CSS = """
    DiffWidget {
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self, diff: UnifiedDiff, *, name: str | None = None, id: str | None = None
    ) -> None:
        super().__init__(name=name, id=id)
        self._diff = diff

    @property
    def diff(self) -> UnifiedDiff:
        return self._diff

    def render(self):  # type: ignore[override]
        text = self._diff.render() or "[dim]No changes proposed.[/dim]"
        return Syntax(text, "diff", theme="ansi_dark", line_numbers=False, word_wrap=False)


class DiffModal(ModalScreen[bool]):
    """Apply-or-discard gate for a :class:`UnifiedDiff`.

    Returns ``True`` from ``app.push_screen`` when the user confirms
    *Apply*, ``False`` when they cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("a", "apply", "Apply", show=True),
    ]

    DEFAULT_CSS = """
    DiffModal {
        align: center middle;
    }
    #diff-modal {
        width: 80%;
        height: 80%;
        padding: 1 2;
    }
    #diff-actions {
        height: 3;
        align: right middle;
    }
    Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        diff: UnifiedDiff,
        *,
        title: str = "Review changes",
        on_apply: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._diff = diff
        self._title = title
        self._on_apply = on_apply

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-modal"):
            yield Static(f"[bold]{self._title}[/bold]")
            yield DiffWidget(self._diff, id="diff-modal-widget")
            with Horizontal(id="diff-actions"):
                yield Button("Apply", id="apply", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "apply":
            self.action_apply()
        elif event.button.id == "cancel":
            self.action_cancel()

    def action_apply(self) -> None:
        if self._on_apply is not None:
            self._on_apply()
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


__all__ = ["DiffModal", "DiffWidget"]
