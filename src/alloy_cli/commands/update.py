"""``alloy update`` — atomic upgrade of pinned components."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from alloy_cli.core import update as _update
from alloy_cli.core.lockfile import AlloyLockfile, read_lock
from alloy_cli.core.project import PROJECT_FILE, AlloyDir, read


def _load_lock(layout: AlloyDir) -> AlloyLockfile:
    if layout.lockfile.exists():
        return read_lock(layout.lockfile)
    return AlloyLockfile(
        schema_version="1.0.0",
        alloy=None,
        alloy_codegen=None,
        alloy_devices_yml=None,
        alloy_cli=None,
    )


@click.command("update", help="Atomically upgrade pinned alloy components.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the upgrades that would happen without applying.",
)
@click.option(
    "--frozen",
    is_flag=True,
    default=False,
    help="Refuse any change.  Useful for CI.",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
)
def update_command(dry_run: bool, frozen: bool, project_dir: Path) -> None:
    project_dir = project_dir.resolve()
    config = read(project_dir / PROJECT_FILE)
    layout = AlloyDir(root=project_dir)
    lock = _load_lock(layout)
    upgrades = _update.resolve_upgrades(config, lock)
    changed = [u for u in upgrades if u.is_change()]

    console = Console()
    if not changed:
        console.print("[green]✓ All components up to date.[/green]")
        return

    for upgrade in changed:
        console.print(
            f"  {upgrade.component}: [yellow]{upgrade.current or '(unset)'}[/yellow] → "
            f"[green]{upgrade.target}[/green]"
        )

    if frozen:
        raise click.ClickException("--frozen forbids any change; refusing.")

    if dry_run:
        console.print("[dim]--dry-run: lockfile not modified.[/dim]")
        return

    new_lock = _update.apply_upgrades(project_dir, upgrades=upgrades, config=config, dry_run=False)
    console.print(
        f"[green]✓ Updated[/green] {layout.lockfile} (alloy={new_lock.alloy}, "
        f"alloy-codegen={new_lock.alloy_codegen})"
    )


__all__ = ["update_command"]
