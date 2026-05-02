"""``alloy new`` — scaffold a fresh project from a board or chip."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.scaffold import (
    SUPPORTED_LICENSES,
    ScaffoldError,
    ScaffoldRequest,
    ScaffoldResult,
    scaffold,
)


def _parse_device(value: str) -> tuple[str, str, str]:
    parts = value.split("/")
    if len(parts) != 3 or any(not p for p in parts):
        raise click.BadParameter(
            f"--device {value!r} must be VENDOR/FAMILY/DEVICE (e.g. st/stm32g0/stm32g071rb)."
        )
    return parts[0], parts[1], parts[2]


def _git_init(dest: Path) -> bool:
    """Initialise a git repo with a single ``alloy new`` commit.

    Returns True on success, False (silently) when ``git`` is missing.
    """
    try:
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=dest,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=dest,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=alloy@local",
                "-c",
                "user.name=alloy-cli",
                "commit",
                "--quiet",
                "--no-gpg-sign",
                "-m",
                "alloy new",
            ],
            cwd=dest,
            check=True,
            capture_output=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


@click.command("new", help="Scaffold a new alloy-cli firmware project.")
@click.argument("name")
@click.option(
    "--board",
    "board_id",
    metavar="ID",
    default=None,
    help="Board id (run `alloy boards` to list).  Mutually exclusive with --device.",
)
@click.option(
    "--device",
    "device_str",
    metavar="VENDOR/FAMILY/DEVICE",
    default=None,
    help="Chip-only project: e.g. st/stm32g0/stm32g071rb.  Mutually exclusive with --board.",
)
@click.option(
    "--license",
    "license_id",
    type=click.Choice(SUPPORTED_LICENSES, case_sensitive=False),
    default="MIT",
    show_default=True,
    help="License header for the generated LICENSE file.",
)
@click.option(
    "--author",
    default="Alloy User",
    show_default=True,
    help="Copyright holder for the LICENSE template.",
)
@click.option(
    "--git/--no-git",
    "init_git",
    default=True,
    show_default=True,
    help="Initialise a git repo with a single 'alloy new' commit.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Allow scaffolding into a non-empty directory.",
)
@click.option(
    "--path",
    "path_override",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Destination directory.  Defaults to ./<NAME>.",
)
def new_command(
    name: str,
    board_id: str | None,
    device_str: str | None,
    license_id: str,
    author: str,
    init_git: bool,
    force: bool,
    path_override: Path | None,
) -> None:
    """Generate a complete project tree from board or chip selection."""
    console = Console()

    if board_id is None and device_str is None:
        raise click.UsageError(
            "Specify either --board or --device.  "
            "Run `alloy boards` to list known boards or `alloy devices` "
            "to browse chips."
        )
    if board_id is not None and device_str is not None:
        raise click.UsageError("--board and --device are mutually exclusive.")

    device = _parse_device(device_str) if device_str else None
    destination = (path_override or Path(name)).expanduser()

    request = ScaffoldRequest(
        name=name,
        destination=destination,
        board_id=board_id,
        device=device,
        license=license_id,
        author=author,
        init_git=init_git,
        force=force,
    )
    try:
        result: ScaffoldResult = scaffold(request)
    except ScaffoldError as exc:
        raise click.ClickException(str(exc)) from exc
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    if init_git:
        _git_init(result.destination)

    rel = (
        result.destination.relative_to(Path.cwd())
        if result.destination.is_relative_to(Path.cwd())
        else result.destination
    )
    next_steps = (
        f"[bold]Done![/bold]  Project [cyan]{result.name}[/cyan] scaffolded at "
        f"[green]{rel}[/green].\n\n"
        f"Target: {result.target_label}\n\n"
        f"Next steps:\n"
        f"  cd {rel}\n"
        f"  cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug\n"
        f"  cmake --build build\n"
    )
    console.print(Panel.fit(next_steps, border_style="cyan", title="alloy new"))


__all__ = ["new_command"]
