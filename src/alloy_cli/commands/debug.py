"""``alloy debug`` Click command — spawn probe-rs gdb-server + attach GDB."""

from __future__ import annotations

import signal
import subprocess
import time
from pathlib import Path

import click
from rich.console import Console

from alloy_cli.core import debug as _debug
from alloy_cli.core import flash as _flash
from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.project import PROJECT_FILE, AlloyDir, read


def _resolve_elf(project_dir: Path, elf_override: Path | None) -> Path:
    if elf_override is not None:
        return elf_override.resolve()
    layout = AlloyDir(root=project_dir)
    build_dir = layout.base / "build"
    if build_dir.is_dir():
        elfs = sorted(build_dir.rglob("*.elf"))
        if elfs:
            return elfs[0]
    raise click.ClickException("No ELF found.  Run `alloy build` first or pass --elf.")


def _resolve_chip(project_dir: Path, target: str | None) -> str:
    config = read(project_dir / PROJECT_FILE)
    if target:
        return target
    if config.chip is not None:
        return config.chip.device
    if config.board is not None:
        from alloy_cli.core import boards as _boards

        try:
            manifest = _boards.lookup(config.board.id)
            return manifest.device
        except Exception as exc:
            raise click.ClickException(
                f"Could not resolve chip from board {config.board.id!r}: {exc}.  "
                "Pass --target <chip>."
            ) from exc
    raise click.ClickException("alloy.toml has neither [board] nor [chip]; pass --target <chip>.")


@click.command("debug", help="Launch probe-rs gdb-server + attach GDB.")
@click.option(
    "--probe",
    "probe_kind",
    default="auto",
    show_default=True,
    help="Probe selector forwarded to probe-rs.",
)
@click.option(
    "--target",
    default=None,
    help="Override the chip name (default: from alloy.toml).",
)
@click.option(
    "--gdb-ui",
    default=None,
    help="Override the GDB binary (default: ALLOY_GDB env var, then arm-none-eabi-gdb).",
)
@click.option(
    "--gdb-port",
    type=int,
    default=1337,
    show_default=True,
    help="TCP port for the gdb-server.",
)
@click.option(
    "--elf",
    "elf_override",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to the firmware ELF.",
)
@click.option(
    "--project-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the gdb-server + GDB invocations without running them.",
)
def debug_command(
    probe_kind: str,
    target: str | None,
    gdb_ui: str | None,
    gdb_port: int,
    elf_override: Path | None,
    project_dir: Path,
    dry_run: bool,
) -> None:
    """Spawn a gdb-server in the background and attach the user's GDB."""
    console = Console()
    project_dir = project_dir.resolve()
    elf = _resolve_elf(project_dir, elf_override)
    chip = _resolve_chip(project_dir, target)

    try:
        # Probe selection happens up-front so misconfiguration fails fast.
        probes = _flash.detect_probes()
        _flash.select_probe(probes, requested=probe_kind)

        session = _debug.build_invocation(
            elf=elf,
            chip=chip,
            gdb_ui=gdb_ui,
            probe_kind=probe_kind,
            gdb_port=gdb_port,
        )
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        console.print("[bold]gdb-server[/bold]: " + " ".join(session.server_args))
        console.print("[bold]gdb       [/bold]: " + " ".join(session.gdb_args))
        return

    console.print(f"[bold]Starting gdb-server[/bold] on port {session.gdb_port} …")
    server = subprocess.Popen(
        list(session.server_args),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        time.sleep(1)  # give the server a moment to bind
        console.print(f"[bold]Attaching[/bold] {session.gdb_args[0]} …")
        gdb = subprocess.Popen(list(session.gdb_args))
        try:
            gdb.wait()
        except KeyboardInterrupt:
            gdb.send_signal(signal.SIGINT)
            gdb.wait()
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=2)
            except subprocess.TimeoutExpired:
                server.kill()


__all__ = ["debug_command"]
