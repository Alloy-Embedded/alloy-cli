"""``alloy ui`` — launch the Textual app shell."""

from __future__ import annotations

from pathlib import Path

import click

from alloy_cli.core.project import PROJECT_FILE
from alloy_cli.tui.app import TuiApp


@click.command("ui", help="Launch the alloy Textual UI.")
@click.option(
    "--theme",
    "theme",
    default=None,
    help="Theme name (default: $ALLOY_TUI_THEME or default_dark).",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml.",
)
def ui_command(theme: str | None, project_dir: Path) -> None:
    """Open the TUI app shell.

    Lands on the Dashboard when ``alloy.toml`` is present in
    ``--project-dir``; otherwise opens the Welcome screen so the
    user can run the onboarding wizard via the command palette.
    """
    if theme:
        import os

        os.environ["ALLOY_TUI_THEME"] = theme

    # Importing this side-effect-registers Dashboard / Onboarding /
    # Welcome with the global registry.
    import alloy_cli.tui.screens  # noqa: F401
    from alloy_cli.tui.screens.dashboard import DashboardScreen
    from alloy_cli.tui.screens.welcome import WelcomeScreen

    project_dir = project_dir.resolve()
    landing = (
        DashboardScreen(project_dir=project_dir)
        if (project_dir / PROJECT_FILE).exists()
        else WelcomeScreen()
    )
    TuiApp(initial_screen=landing).run()


__all__ = ["ui_command"]
