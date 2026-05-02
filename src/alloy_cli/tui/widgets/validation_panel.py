"""``ValidationPanel`` — colour + glyph list of :class:`Diagnostic`s."""

from __future__ import annotations

from collections.abc import Iterable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from alloy_cli.core.diagnostics import Diagnostic
from alloy_cli.tui.theme import glyph_for_severity

_CSS_FOR_SEVERITY = {"error": "diag-error", "warning": "diag-warning", "info": "diag-info"}


class ValidationPanel(Widget):
    """Render a list of :class:`Diagnostic`s with paired colour + glyph."""

    DEFAULT_CSS = """
    ValidationPanel {
        height: auto;
        padding: 0 1;
    }
    ValidationPanel .diag-line {
        height: auto;
    }
    """

    def __init__(
        self,
        diagnostics: Iterable[Diagnostic] = (),
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id)
        self._diagnostics: tuple[Diagnostic, ...] = tuple(diagnostics)

    def compose(self) -> ComposeResult:
        with Vertical():
            if not self._diagnostics:
                yield Static("[dim]No diagnostics.[/dim]")
                return
            for diag in self._diagnostics:
                glyph = glyph_for_severity(diag.severity)
                css = _CSS_FOR_SEVERITY.get(diag.severity, "diag-info")
                head = f"{glyph} [{diag.code}] {diag.message}"
                if diag.path:
                    head += f"  [dim]({diag.path})[/dim]"
                line = Static(head, classes=f"diag-line {css}")
                yield line
                if diag.suggestions:
                    yield Static(
                        f"   suggestions: {', '.join(diag.suggestions[:6])}",
                        classes="diag-line",
                    )

    def update_diagnostics(self, diagnostics: Iterable[Diagnostic]) -> None:
        """Replace the displayed diagnostics + recompose."""
        self._diagnostics = tuple(diagnostics)
        self.refresh(recompose=True)


__all__ = ["ValidationPanel"]
