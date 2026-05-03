"""``alloy setup`` — guided onboarding wizard for a fresh machine.

The friendliest entry point of the CLI: walks the user from
"I just cloned this repo" (or "I have nothing yet") to a working
toolchain in three steps:

1. **Detect project state** at ``--project-dir`` (default: CWD).
   - Has ``alloy.toml`` → resolve the family from it; skip scaffolding.
   - No ``alloy.toml`` → prompt for ``--board`` (or use ``--board`` /
     ``--family`` overrides) and scaffold first.
2. **Resolve + render the install plan** for the family.
3. **Install** through the shared orchestrator (the same call path
   ``alloy new`` and ``alloy doctor --fix`` use).  Vendor tools are
   skipped with their install_doc URL — never auto-fetched.

Wave 4 will plug a Textual ``OnboardingScreen`` in front of this
flow when STDIN is a TTY and ``--no-tui`` is not set.  Until then
the line-based wizard is the only path; ``--no-tui`` is a no-op
documented as the future opt-out.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from alloy_cli.commands._install_view import (
    make_event_logger,
    render_install_plan,
    render_install_summary,
)
from alloy_cli.core import boards as _boards
from alloy_cli.core import toolchain_orchestrator as _orch
from alloy_cli.core import toolchain_registry as _registry
from alloy_cli.core.errors import (
    AlloyCliError,
    BoardNotFoundError,
    FamilyToolchainError,
    OnboardingCancelledError,
)
from alloy_cli.core.project import PROJECT_FILE, read
from alloy_cli.core.scaffold import (
    ScaffoldError,
    ScaffoldRequest,
    ScaffoldResult,
    scaffold,
)
from alloy_cli.core.toolchain_registry import FamilyManifest

# ---------------------------------------------------------------------------
# TTY probe (broken out for the same reason as commands/new.py — Click's
# CliRunner owns sys.stdin during invoke(), so tests need a stable seam).
# ---------------------------------------------------------------------------


def _is_stdin_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Family / board resolution
# ---------------------------------------------------------------------------


def _resolve_existing_project_family(
    project_dir: Path, family_override: str | None
) -> FamilyManifest | None:
    """When ``alloy.toml`` exists, resolve the family it pins.

    ``family_override`` (``--family``) wins over the project's pinned
    family for the install path — useful when the project pins a
    family alloy-cli doesn't ship a manifest for and the user wants
    to retry under a different one.  Returns ``None`` when no manifest
    can be resolved.
    """
    if family_override is not None:
        return _registry.load_family(family_override)
    config = read(project_dir / PROJECT_FILE)
    return _registry.resolve_for_project(config)


def _line_based_board_picker(console: Console) -> str:
    """Render the catalogue as a numbered list and read one line of input.

    Falls back to a no-board error when ``ALLOY_BOARDS_ROOT`` is unset
    (the typical CI shape) — the user has to pass ``--board`` or
    ``--family`` explicitly in that case.
    """
    catalog = _boards.load_catalog()
    if not catalog:
        raise click.ClickException(
            "No board catalogue available.  Pass --board or --family, "
            "or run `alloy boards` to populate the cache."
        )

    by_tier: dict[int, list[_boards.BoardSummary]] = {}
    for summary in catalog:
        by_tier.setdefault(summary.tier, []).append(summary)

    table = Table(
        title="Pick a board (or pass --board / --family next time)",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("#", justify="right")
    table.add_column("board")
    table.add_column("family")
    table.add_column("mcu")
    table.add_column("tier", justify="right")

    flat: list[_boards.BoardSummary] = []
    counter = 1
    for tier in sorted(by_tier):
        for summary in by_tier[tier]:
            flat.append(summary)
            table.add_row(
                str(counter),
                summary.board_id,
                summary.family,
                summary.mcu,
                str(summary.tier),
            )
            counter += 1
    console.print(table)
    selection = click.prompt(
        "Enter the number of the board to set up",
        type=click.IntRange(1, len(flat)),
    )
    return flat[selection - 1].board_id


def _resolve_board_id(
    board_id: str | None,
    family: str | None,
    *,
    auto: bool,
    no_tui: bool,
    console: Console,
) -> str:
    """Pick the board the wizard will scaffold against, prompting if needed."""
    del no_tui  # Wave-3 always uses the line-based prompt; Wave-3 group 5
    # will branch on (tty and not no_tui) → Textual.
    if board_id is not None:
        return board_id
    if family is not None:
        # Find any board whose family matches; prefer tier-1.
        catalog = _boards.load_catalog()
        candidates = [s for s in catalog if s.family == family]
        if not candidates:
            raise click.ClickException(
                f"No boards in catalog for family {family!r}.  Pass --board to pin one explicitly."
            )
        candidates.sort(key=lambda s: (s.tier, s.board_id))
        return candidates[0].board_id
    if auto:
        raise click.UsageError("--auto outside a project requires --board or --family.")
    if not _is_stdin_tty():
        raise click.UsageError("STDIN is not a TTY; --board or --family must be passed.")
    return _line_based_board_picker(console)


# ---------------------------------------------------------------------------
# Scaffolding step (when no project exists yet)
# ---------------------------------------------------------------------------


def _scaffold_project(*, project_dir: Path, board_id: str, console: Console) -> ScaffoldResult:
    """Run the same scaffolder ``alloy new`` uses, but at ``project_dir``."""
    request = ScaffoldRequest(
        name=project_dir.name,
        destination=project_dir,
        board_id=board_id,
        device=None,
        license="MIT",
        author="Alloy User",
        init_git=False,
        force=False,
    )
    try:
        result = scaffold(request)
    except ScaffoldError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(
        f"[green]✓ Scaffolded[/green] [cyan]{result.name}[/cyan] at "
        f"[bold]{result.destination}[/bold] (target: {result.target_label})."
    )
    return result


# ---------------------------------------------------------------------------
# Install step
# ---------------------------------------------------------------------------


def _run_install_phase(
    *,
    manifest: FamilyManifest,
    project_root: Path,
    console: Console,
    auto: bool,
) -> _orch.InstallReport | None:
    """Render the plan, prompt (when interactive + not auto), dispatch."""
    plan, warnings = _orch.plan_install(manifest)
    if not plan:
        return None

    render_install_plan(
        console,
        manifest,
        plan,
        title=f"Install plan for {manifest.family_id}",
    )
    for warning in warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")

    if not auto and _is_stdin_tty():
        if not click.confirm("Install now?", default=True):
            console.print("[yellow]Skipped.[/yellow]")
            return None

    console.print(f"\n[bold]Installing toolchain for {manifest.family_id}…[/bold]")
    try:
        report = _orch.install_family(
            manifest,
            project_root=project_root,
            on_event=make_event_logger(console),
        )
    except KeyboardInterrupt as exc:  # pragma: no cover — SIGINT path
        raise OnboardingCancelledError(
            "Interrupted before the install completed.",
        ) from exc
    render_install_summary(console, report)
    return report


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command(
    "setup",
    help=(
        "Guided onboarding for a fresh machine: detect or scaffold a "
        "project, then install its toolchain through the shared "
        "orchestrator (the same path `alloy new` and `alloy doctor "
        "--fix` use)."
    ),
)
@click.option(
    "--board",
    "board_id",
    metavar="ID",
    default=None,
    help="Pre-pick a board (skips the picker step).",
)
@click.option(
    "--family",
    metavar="FAMILY",
    default=None,
    help="Pre-pick a family; mutually exclusive with --board.",
)
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help=(
        "Suppress every interactive prompt with the default answer "
        "(Y on each install confirmation)."
    ),
)
@click.option(
    "--no-tui",
    is_flag=True,
    default=False,
    help=(
        "Force the line-based wizard even when STDIN is a TTY.  "
        "(Wave 3: line-based is the only path; this flag is a "
        "forward-compatible no-op.)"
    ),
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root.  Defaults to the current directory.",
)
def setup_command(
    board_id: str | None,
    family: str | None,
    auto: bool,
    no_tui: bool,
    project_dir: Path,
) -> None:
    """Run the wizard."""
    if board_id is not None and family is not None:
        raise click.UsageError("--board and --family are mutually exclusive.")

    project_dir = project_dir.resolve()
    console = Console()
    has_project = (project_dir / PROJECT_FILE).exists()

    try:
        if has_project:
            console.print(f"[bold]Existing project[/bold] at [cyan]{project_dir}[/cyan]")
            try:
                manifest = _resolve_existing_project_family(project_dir, family)
            except (FamilyToolchainError, AlloyCliError) as exc:
                raise click.ClickException(str(exc)) from exc
            if manifest is None:
                raise click.ClickException(
                    f"Project at {project_dir} doesn't resolve to a known "
                    "family.  Pass --family to override."
                )
        else:
            # Fresh project flow: scaffold first, then install.
            try:
                resolved_board = _resolve_board_id(
                    board_id, family, auto=auto, no_tui=no_tui, console=console
                )
            except (BoardNotFoundError, FamilyToolchainError) as exc:
                raise click.ClickException(str(exc)) from exc
            _scaffold_project(
                project_dir=project_dir,
                board_id=resolved_board,
                console=console,
            )
            try:
                manifest = _resolve_existing_project_family(project_dir, None)
            except (FamilyToolchainError, AlloyCliError) as exc:
                raise click.ClickException(str(exc)) from exc
            if manifest is None:
                raise click.ClickException(
                    f"Scaffolded project at {project_dir} doesn't resolve "
                    "to a known family — this is a bug; please report it."
                )

        try:
            _run_install_phase(
                manifest=manifest,
                project_root=project_dir,
                console=console,
                auto=auto,
            )
        except OnboardingCancelledError as exc:
            console.print(f"\n[yellow]Onboarding cancelled:[/yellow] {exc}")
            console.print(
                f"[dim]Resume with [bold]alloy toolchain install[/bold] in {project_dir}.[/dim]"
            )
            sys.exit(130)
    except click.UsageError:
        raise
    except click.ClickException:
        raise
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    rel = (
        project_dir.relative_to(Path.cwd())
        if project_dir.is_relative_to(Path.cwd())
        else project_dir
    )
    next_steps = (
        f"[bold green]✓ Setup complete.[/bold green]\n\n"
        f"Project: [cyan]{rel}[/cyan]\n"
        f"Family:  [cyan]{manifest.family_id}[/cyan]\n\n"
        f"Next steps:\n"
        f"  cd {rel}\n"
        f"  alloy build\n"
        f"  alloy flash\n"
        f"  alloy ui   [dim]# launch the TUI dashboard[/dim]\n"
    )
    console.print(Panel.fit(next_steps, border_style="cyan", title="alloy setup"))


__all__ = ["setup_command"]
