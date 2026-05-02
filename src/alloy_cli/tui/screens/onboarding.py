"""``OnboardingScreen`` — multi-step wizard for first-time users."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.scaffold import (
    PROJECT_NAME_RE,
    SUPPORTED_LICENSES,
    ScaffoldRequest,
    scaffold,
    validate_project_name,
)
from alloy_cli.tui.registry import register_screen

_STEPS = (
    "Project name",
    "Board / device",
    "Clock profile",
    "Starter peripheral",
    "Confirm + apply",
    "Build now?",
)


@dataclass
class _OnboardingState:
    """Per-step inputs the wizard collects."""

    name: str = ""
    board_id: str | None = None
    device: tuple[str, str, str] | None = None
    clock_profile: str | None = None
    starter_peripheral_kind: str | None = None
    license: str = "MIT"
    init_git: bool = True
    skipped: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "name": self.name,
            "board_id": self.board_id,
            "device": list(self.device) if self.device else None,
            "clock_profile": self.clock_profile,
            "starter_peripheral_kind": self.starter_peripheral_kind,
            "license": self.license,
            "init_git": self.init_git,
            "skipped": sorted(self.skipped),
        }
        return out

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> _OnboardingState:
        device = payload.get("device")
        return cls(
            name=str(payload.get("name", "")),
            board_id=payload.get("board_id"),  # type: ignore[arg-type]
            device=tuple(device) if isinstance(device, list) and len(device) == 3 else None,  # type: ignore[arg-type]
            clock_profile=payload.get("clock_profile"),  # type: ignore[arg-type]
            starter_peripheral_kind=payload.get("starter_peripheral_kind"),  # type: ignore[arg-type]
            license=str(payload.get("license", "MIT")),
            init_git=bool(payload.get("init_git", True)),
            skipped=set(payload.get("skipped", []) or []),  # type: ignore[arg-type]
        )


def state_path(root: Path) -> Path:
    """Where the wizard stashes partial state for resume."""
    return root / ".alloy" / "onboarding.json"


def persist_state(root: Path, state: _OnboardingState) -> None:
    target = state_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def load_state(root: Path) -> _OnboardingState | None:
    target = state_path(root)
    if not target.exists():
        return None
    try:
        return _OnboardingState.from_dict(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


class OnboardingScreen(Screen[_OnboardingState | None]):
    """Six-step wizard from "no project" to "buildable project"."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save_and_exit", "Save"),
    ]

    DEFAULT_CSS: ClassVar[str] = """
    OnboardingScreen Vertical {
        padding: 0 2;
    }
    OnboardingScreen .step-counter {
        text-style: bold;
        color: $accent;
    }
    OnboardingScreen .actions {
        padding-top: 1;
    }
    """

    def __init__(self, root: Path, state: _OnboardingState | None = None) -> None:
        super().__init__()
        self._root = root.resolve()
        self._state = state or _OnboardingState()
        self._step = 0

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Static(
                f"Step {self._step + 1}/{len(_STEPS)}: [b]{_STEPS[self._step]}[/b]",
                classes="step-counter",
            )
            yield from self._compose_step()
            with Horizontal(classes="actions"):
                yield Button("Skip", id="skip", variant="default")
                yield Button("Next", id="next", variant="success")
        yield Footer()

    def _compose_step(self) -> ComposeResult:
        if self._step == 0:
            yield Input(
                value=self._state.name,
                placeholder="firmware",
                id="step-name",
            )
            yield Static(f"[dim]Name pattern: {PROJECT_NAME_RE.pattern}[/dim]")
        elif self._step == 1:
            yield Input(
                value=self._state.board_id or "",
                placeholder="board id (e.g. nucleo_g071rb) — board-picker arrives in #10",
                id="step-board",
            )
            yield Static(
                "[dim]Tip: run [bold]alloy boards[/bold] in another shell to see the catalogue.[/dim]"
            )
        elif self._step == 2:
            yield Input(
                value=self._state.clock_profile or "",
                placeholder="default_pll_64mhz",
                id="step-clock",
            )
        elif self._step == 3:
            yield Input(
                value=self._state.starter_peripheral_kind or "",
                placeholder="(optional) e.g. uart, gpio, spi, i2c",
                id="step-starter",
            )
        elif self._step == 4:
            yield Static(self._render_summary())
        elif self._step == 5:
            yield Static("Project scaffolded.  Press [b]Next[/b] to land on the Dashboard.")

    def _render_summary(self) -> str:
        bullets = [
            f"name              : {self._state.name or '(unset)'}",
            f"board / device    : {self._state.board_id or self._state.device or '(unset)'}",
            f"clock_profile     : {self._state.clock_profile or '(skipped)'}",
            f"starter peripheral: {self._state.starter_peripheral_kind or '(skipped)'}",
            f"license           : {self._state.license}",
            f"init_git          : {self._state.init_git}",
        ]
        return "\n".join(f"  • {b}" for b in bullets)

    # ------------------------------------------------------------------
    # Step handling
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "skip":
            self._state.skipped.add(_STEPS[self._step])
            self._advance()
        elif event.button.id == "next":
            self._capture_step()
            if self._step == 4:
                # Confirm step → apply scaffold.
                ok = self._apply_scaffold()
                if not ok:
                    return
            if self._step + 1 >= len(_STEPS):
                self._finalise()
                return
            self._advance()

    def _capture_step(self) -> None:
        if self._step == 0:
            value = self.query_one("#step-name", Input).value.strip()
            if value:
                try:
                    validate_project_name(value)
                except ValueError as exc:
                    self.notify(str(exc), severity="error")
                    return
                self._state.name = value
        elif self._step == 1:
            value = self.query_one("#step-board", Input).value.strip()
            if value:
                self._state.board_id = value
                self._state.device = None
        elif self._step == 2:
            value = self.query_one("#step-clock", Input).value.strip()
            self._state.clock_profile = value or None
        elif self._step == 3:
            value = self.query_one("#step-starter", Input).value.strip().lower()
            self._state.starter_peripheral_kind = value or None

    def _advance(self) -> None:
        if self._step + 1 < len(_STEPS):
            self._step += 1
            persist_state(self._root, self._state)
            self.refresh(recompose=True)

    def _apply_scaffold(self) -> bool:
        if not self._state.name:
            self.notify("Name is required before applying.", severity="error")
            return False
        if not (self._state.board_id or self._state.device):
            self.notify("Choose a board or device before applying.", severity="error")
            return False
        request = ScaffoldRequest(
            name=self._state.name,
            destination=self._root / self._state.name,
            board_id=self._state.board_id,
            device=self._state.device,
            license=self._state.license if self._state.license in SUPPORTED_LICENSES else "MIT",
            init_git=self._state.init_git,
            force=False,
        )
        try:
            scaffold(request)
        except (AlloyCliError, OSError) as exc:
            self.notify(f"Scaffold failed: {exc}", severity="error")
            return False
        return True

    def _finalise(self) -> None:
        persist_state(self._root, self._state)
        self.dismiss(self._state)

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save_and_exit(self) -> None:
        persist_state(self._root, self._state)
        self.dismiss(self._state)


@register_screen(
    "onboarding",
    title="Onboarding",
    description="First-run wizard — name, board, clocks, starter peripheral",
)
def make_onboarding() -> Screen:
    return OnboardingScreen(root=Path.cwd())


__all__ = ["OnboardingScreen", "_OnboardingState", "load_state", "make_onboarding", "persist_state"]
