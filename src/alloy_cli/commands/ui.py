"""``alloy ui`` — launch the Textual app shell."""

from __future__ import annotations

import click

from alloy_cli.tui.app import TuiApp


@click.command("ui", help="Launch the alloy Textual UI.")
@click.option(
    "--theme",
    "theme",
    default=None,
    help="Theme name (default: $ALLOY_TUI_THEME or default_dark).",
)
def ui_command(theme: str | None) -> None:
    """Open the TUI app shell.

    With no project in CWD this lands on the Welcome screen until
    later proposals add the Dashboard.
    """
    if theme:
        import os

        os.environ["ALLOY_TUI_THEME"] = theme

    # Ensure the bundled screens are imported so they register
    # themselves with the global registry.
    import alloy_cli.tui.screens  # noqa: F401

    app = TuiApp()
    app.run()


__all__ = ["ui_command"]
