"""``alloy new`` — scaffold a fresh project from a board or chip."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.project import PROJECT_FILE, parse, read, write
from alloy_cli.core.scaffold import (
    SUPPORTED_LICENSES,
    ScaffoldError,
    ScaffoldRequest,
    ScaffoldResult,
    scaffold,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXAMPLES_ROOT = _REPO_ROOT / "docs" / "EXAMPLES"


def _example_root(name: str) -> Path:
    """Resolve the example directory for a `--from-example` value."""
    candidate = _EXAMPLES_ROOT / name
    if not (candidate / PROJECT_FILE).exists():
        available = ", ".join(sorted(p.name for p in _EXAMPLES_ROOT.iterdir() if p.is_dir())) or "<none>"
        raise click.BadParameter(
            f"Unknown example {name!r}.  Available: {available}.",
            param_hint="--from-example",
        )
    return candidate


def _apply_example(destination: Path, project_name: str, example: Path) -> None:
    """Overlay the example's alloy.toml on top of the scaffolded tree."""
    body = (example / PROJECT_FILE).read_text(encoding="utf-8")
    # Cheap re-parent: parse, swap `[project].name`, write back.
    import tomllib

    payload = tomllib.loads(body)
    payload.setdefault("project", {})["name"] = project_name
    parsed = parse(payload)
    write(destination / PROJECT_FILE, parsed)


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
@click.option(
    "--from-example",
    "from_example",
    metavar="NAME",
    default=None,
    help=(
        "Scaffold from a docs/EXAMPLES entry (e.g. 01-blinky, "
        "02-uart-echo).  Mutually exclusive with --board / --device."
    ),
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
    from_example: str | None,
) -> None:
    """Generate a complete project tree from board, chip, or example."""
    console = Console()

    if from_example is not None:
        if board_id is not None or device_str is not None:
            raise click.UsageError(
                "--from-example is mutually exclusive with --board / --device."
            )
        example_root = _example_root(from_example)
        # Read the example's target so the scaffold call can resolve it.
        example_config = read(example_root / PROJECT_FILE)
        if example_config.board is not None:
            board_id = example_config.board.id
        elif example_config.chip is not None:
            chip = example_config.chip
            device_str = f"{chip.vendor}/{chip.family}/{chip.device}"
        else:
            raise click.ClickException(
                f"Example {from_example!r} is missing both [board] and "
                "[chip] — refusing to scaffold."
            )

    if board_id is None and device_str is None:
        raise click.UsageError(
            "Specify either --board, --device, or --from-example.  "
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

    if from_example is not None:
        # Overlay the example's full alloy.toml (peripherals,
        # clock profile, etc.) on top of the bare scaffold.
        _apply_example(result.destination, name, _example_root(from_example))

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
