"""``alloy new`` — scaffold a fresh project from a board or chip.

Wave 3 extends the verb with a post-scaffold install prompt: when
STDIN is a TTY (or ``--install-toolchain`` is explicit) the command
offers to download + verify + extract the family's required tier
right after the scaffold lands, dispatching through
:func:`alloy_cli.core.toolchain_orchestrator.install_family` so the
walk shares one source of truth with ``alloy doctor --fix``,
``alloy setup``, the TUI Onboarding screen, and the MCP
``toolchain_apply_install_plan`` tool.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from alloy_cli.commands._install_view import (
    make_event_logger,
    render_install_plan,
    render_install_summary,
)
from alloy_cli.core import toolchain_orchestrator as _orch
from alloy_cli.core import toolchain_registry as _registry
from alloy_cli.core.errors import (
    AlloyCliError,
    OnboardingCancelledError,
)
from alloy_cli.core.project import PROJECT_FILE, parse, read, write
from alloy_cli.core.scaffold import (
    SUPPORTED_LICENSES,
    ScaffoldError,
    ScaffoldRequest,
    ScaffoldResult,
    scaffold,
)
from alloy_cli.core.toolchain_registry import FamilyManifest

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


# ---------------------------------------------------------------------------
# Post-scaffold toolchain install (Wave 3)
# ---------------------------------------------------------------------------


def _is_stdin_tty() -> bool:
    """TTY probe broken out as a module-level helper so tests can
    monkeypatch it without having to swap ``sys.stdin`` (which Click's
    :class:`CliRunner` already owns during ``invoke()``).
    """
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _should_offer_install(*, install_flag: bool | None, tty: bool) -> bool:
    """Decide whether to run the post-scaffold toolchain install.

    Matches design D3:
    - explicit ``--install-toolchain`` / ``--no-install-toolchain``
      always wins.
    - default Y in a TTY (the user can answer the prompt).
    - default N otherwise (CI, subprocess piping — never block).

    Returning True means "we will dispatch the install (after a
    confirmation prompt unless ``--auto`` is set)".  Returning False
    means "skip silently and tell the user how to install later".
    """
    if install_flag is True:
        return True
    if install_flag is False:
        return False
    return tty


def _resolve_family_for_project(destination: Path) -> FamilyManifest | None:
    """Look up the family manifest for the project we just scaffolded.

    Returns ``None`` when the alloy.toml doesn't pin a known family
    (e.g. chip-only project for a family we don't ship a manifest
    for) — in that case we silently skip the install offer.
    """
    toml_path = destination / PROJECT_FILE
    if not toml_path.exists():
        return None
    try:
        config = read(toml_path)
        return _registry.resolve_for_project(config)
    except AlloyCliError:
        return None


def _run_post_scaffold_install(
    *,
    console: Console,
    project_root: Path,
    manifest: FamilyManifest,
    auto: bool,
    interactive: bool,
) -> _orch.InstallReport | None:
    """Render the plan, prompt (when interactive + not auto), dispatch.

    Returns the :class:`InstallReport` on a real install, or ``None``
    when the user answered N at the prompt.  Raises
    :class:`OnboardingCancelledError` when SIGINT lands mid-install
    (the caller maps that to exit 130).
    """
    plan, warnings = _orch.plan_install(manifest)
    if not plan:
        # Empty manifest: nothing to do.
        return None

    render_install_plan(console, manifest, plan, title=f"Install plan for {manifest.family_id}")
    for warning in warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")

    actionable_count = sum(1 for item in plan if item.is_actionable)
    skipped_count = len(plan) - actionable_count

    if interactive and not auto:
        proceed = click.confirm(
            f"Install now? ({actionable_count} tool(s) to download, "
            f"{skipped_count} skipped)",
            default=True,
        )
        if not proceed:
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
@click.option(
    "--install-toolchain/--no-install-toolchain",
    "install_flag",
    default=None,
    help=(
        "Install the family's toolchain after scaffolding.  Default "
        "in a TTY: Y (prompts unless --auto).  Default elsewhere: N."
    ),
)
@click.option(
    "--auto",
    is_flag=True,
    default=False,
    help=(
        "Skip every interactive confirmation.  Combine with "
        "--install-toolchain to perform the install non-interactively."
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
    install_flag: bool | None,
    auto: bool,
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

    # ---- Wave 3: post-scaffold toolchain install --------------------
    install_ran = False
    install_skipped_explicitly = install_flag is False
    tty = _is_stdin_tty()
    if _should_offer_install(install_flag=install_flag, tty=tty):
        manifest = _resolve_family_for_project(result.destination)
        if manifest is not None:
            try:
                report = _run_post_scaffold_install(
                    console=console,
                    project_root=result.destination,
                    manifest=manifest,
                    auto=auto,
                    interactive=tty,
                )
            except OnboardingCancelledError as exc:
                console.print(f"\n[yellow]Onboarding cancelled:[/yellow] {exc}")
                console.print(
                    "[dim]Resume any time with [bold]alloy toolchain install[/bold] "
                    f"in {rel}.[/dim]"
                )
                sys.exit(130)
            install_ran = report is not None

    # ---- Always-printed next-steps panel ----------------------------
    next_steps_lines = [
        f"[bold]Done![/bold]  Project [cyan]{result.name}[/cyan] scaffolded at "
        f"[green]{rel}[/green].",
        "",
        f"Target: {result.target_label}",
        "",
        "Next steps:",
        f"  cd {rel}",
    ]
    if not install_ran:
        if install_skipped_explicitly:
            next_steps_lines.append(
                "  alloy toolchain install   [dim]# you passed --no-install-toolchain[/dim]"
            )
        elif not tty:
            next_steps_lines.append(
                "  alloy toolchain install   [dim]# non-TTY: install was deferred[/dim]"
            )
        else:
            # User answered N at the prompt OR no manifest resolved.
            next_steps_lines.append(
                "  alloy toolchain install   [dim]# install the family's toolchain[/dim]"
            )
    next_steps_lines.extend(
        [
            "  alloy build",
            "  alloy flash",
        ]
    )
    console.print(Panel.fit("\n".join(next_steps_lines), border_style="cyan", title="alloy new"))


__all__ = ["new_command"]
