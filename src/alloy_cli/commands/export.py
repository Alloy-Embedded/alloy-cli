"""``alloy export <kind>`` — emit auxiliary configuration files."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from alloy_cli.core import export as _export
from alloy_cli.core.project import PROJECT_FILE, read

EXPORT_KINDS = ("ci", "vscode", "gdb", "bom")


def _write_targets(project_dir: Path, files: dict[Path, str]) -> list[Path]:
    written: list[Path] = []
    for rel, content in files.items():
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
    return written


@click.command("export", help="Emit auxiliary configuration files.")
@click.argument("kind", type=click.Choice(EXPORT_KINDS, case_sensitive=False))
@click.option(
    "--target",
    default=None,
    help="Sub-target (e.g. github / gitlab / jenkins for `alloy export ci`).",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
)
def export_command(kind: str, target: str | None, project_dir: Path) -> None:
    project_dir = project_dir.resolve()
    config = read(project_dir / PROJECT_FILE)
    try:
        files = _export.emit(kind, config, target=target)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    written = _write_targets(project_dir, files)
    console = Console()
    for path in written:
        console.print(f"[green]+[/green] {path.relative_to(project_dir)}")


__all__ = ["EXPORT_KINDS", "export_command"]
