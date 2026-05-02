"""Screen registration so the command palette can discover them."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from textual.screen import Screen


@dataclass(frozen=True, slots=True)
class ScreenEntry:
    """One entry in :class:`ScreenRegistry`."""

    name: str
    title: str
    factory: Callable[[], Screen]
    description: str = ""


class ScreenRegistry:
    """In-process registry of TUI screens.

    The Textual command palette + ``alloy ui`` consume this; later
    proposals call :func:`register_screen` to register their screens
    at import time.
    """

    def __init__(self) -> None:
        self._entries: dict[str, ScreenEntry] = {}

    def register(self, entry: ScreenEntry) -> None:
        self._entries[entry.name] = entry

    def get(self, name: str) -> ScreenEntry | None:
        return self._entries.get(name)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._entries

    def __iter__(self) -> Iterator[ScreenEntry]:
        return iter(sorted(self._entries.values(), key=lambda e: e.name))

    def __len__(self) -> int:
        return len(self._entries)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def remove(self, name: str) -> ScreenEntry | None:
        """Unregister + return the entry for ``name`` (or ``None``).

        Useful for tests that register a fixture screen and want
        to clean up afterwards without touching ``_entries``.
        """
        return self._entries.pop(name, None)

    def clear(self) -> None:
        self._entries.clear()


# Module-level registry — single source of truth.
registry = ScreenRegistry()


def register_screen(
    name: str, *, title: str, description: str = ""
) -> Callable[[Callable[[], Screen]], Callable[[], Screen]]:
    """Decorator: register a screen factory under ``name``.

    Usage::

        @register_screen("dashboard", title="Dashboard")
        def make_dashboard() -> Screen:
            return DashboardScreen()
    """

    def _wrap(factory: Callable[[], Screen]) -> Callable[[], Screen]:
        registry.register(
            ScreenEntry(name=name, title=title, factory=factory, description=description)
        )
        return factory

    return _wrap


__all__ = ["ScreenEntry", "ScreenRegistry", "register_screen", "registry"]
