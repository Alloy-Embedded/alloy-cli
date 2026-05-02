"""``FacetedFilter`` — multi-section toggle group used by Boards / Devices."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static


@dataclass
class Facet:
    """One section of a :class:`FacetedFilter`."""

    name: str
    label: str
    options: tuple[str, ...]
    selected: set[str] = field(default_factory=set)


class FacetedFilter(Widget):
    """A vertical stack of horizontal "chip" rows.

    Click / Enter on a chip toggles the selection.  Posts
    :class:`FilterChanged` whenever the active set changes.
    """

    class FilterChanged(Message):
        def __init__(self, facets: dict[str, frozenset[str]]) -> None:
            super().__init__()
            self.facets = facets

    DEFAULT_CSS = """
    FacetedFilter {
        height: auto;
        padding: 0 1;
    }
    .facet-row {
        height: auto;
    }
    """

    def __init__(
        self,
        facets: Iterable[Facet],
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id)
        self._facets: dict[str, Facet] = {f.name: f for f in facets}

    def compose(self) -> ComposeResult:
        with Vertical():
            for facet in self._facets.values():
                yield Static(f"[bold]{facet.label}[/bold]")
                with Horizontal(classes="facet-row"):
                    for option in facet.options:
                        is_active = option in facet.selected
                        chip = Static(
                            f" {option} ",
                            classes="faceted-chip" + (" -active" if is_active else ""),
                        )
                        chip.styles.margin = (0, 1, 0, 0)
                        chip.can_focus = True
                        chip.tooltip = f"{facet.label}: {option}"
                        chip.id = self._chip_id(facet.name, option)
                        yield chip

    @staticmethod
    def _chip_id(facet_name: str, option: str) -> str:
        return f"facet-{facet_name}-{option}".replace(" ", "_")

    def selected(self) -> dict[str, frozenset[str]]:
        return {name: frozenset(f.selected) for name, f in self._facets.items()}

    def toggle(self, facet_name: str, option: str) -> None:
        facet = self._facets.get(facet_name)
        if facet is None or option not in facet.options:
            return
        if option in facet.selected:
            facet.selected.discard(option)
        else:
            facet.selected.add(option)
        self.post_message(self.FilterChanged(self.selected()))
        self.refresh(recompose=True)

    async def on_click(self, event: events.Click) -> None:
        target = event.widget
        if target is None or not target.id:
            return
        if not target.id.startswith("facet-"):
            return
        # facet-<name>-<option>
        body = target.id[len("facet-") :]
        for facet_name in self._facets:
            prefix = facet_name + "-"
            if body.startswith(prefix):
                option = body[len(prefix) :].replace("_", " ")
                self.toggle(facet_name, option)
                event.stop()
                return


__all__ = ["Facet", "FacetedFilter"]
