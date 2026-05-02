"""``alloy toolchain`` subcommand group — Wave 2 of toolchain-management.

Five verbs over the content-addressed store the manager (group 3)
ships:

* ``install`` — download + verify + extract + pin every required
  + non-vendor recommended tool the family declares.  Vendor
  (EULA-gated) tools are skipped with an explicit log line; we
  never auto-fetch STM32CubeProgrammer / nrfjprog / J-Link.
* ``list`` — render the per-family tool surface annotated with
  installed / missing / vendor state from the local store.
* ``use`` — pin ``<tool>@<version>`` in ``.alloy/toolchain.lock``
  using the active host's pinned SHA256.
* ``prune`` — garbage-collect store entries no project lockfile
  references.
* ``shell`` — spawn the user's ``$SHELL`` (or ``cmd.exe``) with
  ``PATH`` augmented for the lifetime of the subshell.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from alloy_cli.core import lockfile_toolchain as _lockfile
from alloy_cli.core import tool_sources as _ts
from alloy_cli.core import toolchain_manager as _manager
from alloy_cli.core import toolchain_registry as _registry
from alloy_cli.core.errors import (
    AlloyCliError,
    FamilyToolchainInstallerError,
    FamilyToolchainInstallerUnsupportedHostError,
)
from alloy_cli.core.project import PROJECT_FILE, AlloyDir, read
from alloy_cli.core.tool_sources import SourceArtifact
from alloy_cli.core.toolchain_registry import (
    FamilyManifest,
    ToolRequirement,
)

# ---------------------------------------------------------------------------
# Family resolution
# ---------------------------------------------------------------------------


def _validate_family(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Click callback: reject unknown ``--for`` values up front."""
    del ctx, param
    if value is None:
        return None
    known = _registry.known_families()
    if value in known:
        return value
    raise click.BadParameter(
        f"Unknown family {value!r}.  Available: {', '.join(known) or '(none)'}.",
    )


def _resolve_family_or_exit(
    project_dir: Path, family_override: str | None
) -> FamilyManifest:
    """Resolve a manifest from ``--for`` first, then the project's
    ``alloy.toml``.  Exit with a clear message when none resolves —
    every toolchain verb needs a family before it can do anything.
    """
    if family_override is not None:
        return _registry.load_family(family_override)
    toml_path = project_dir / PROJECT_FILE
    if toml_path.exists():
        try:
            config = read(toml_path)
        except AlloyCliError as exc:
            raise click.ClickException(str(exc)) from exc
        manifest = _registry.resolve_for_project(config)
        if manifest is not None:
            return manifest
    raise click.ClickException(
        "No family resolved.  Pass --for <family_id> or run inside a "
        "project whose alloy.toml pins a known family.\n"
        f"Known families: {', '.join(_registry.known_families())}."
    )


# ---------------------------------------------------------------------------
# Plan: per-tool dispatch from manifest entries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ToolPlanItem:
    """One row in the install plan."""

    tool: ToolRequirement
    artifact: SourceArtifact | None  # None for vendor tools
    skip_reason: str  # "" when actionable; populated for vendor / unsupported


def _plan_for_family(
    manifest: FamilyManifest, *, include_optional: bool = False
) -> tuple[list[_ToolPlanItem], list[str]]:
    """Walk the manifest's required + recommended (+ optional?) lists
    and resolve each non-vendor tool into a :class:`SourceArtifact`.

    Returns ``(plan_items, soft_warnings)`` where ``soft_warnings``
    captures non-fatal issues (e.g. unsupported host triple for an
    optional tool) the CLI surfaces but doesn't error on.
    """
    items: list[_ToolPlanItem] = []
    warnings: list[str] = []
    host = _ts.host_triple()

    tiers: list[tuple[str, tuple[ToolRequirement, ...]]] = [
        ("required", manifest.required),
        ("recommended", manifest.recommended),
    ]
    if include_optional:
        tiers.append(("optional", manifest.optional))

    for _tier, tools in tiers:
        for tool in tools:
            if tool.is_vendor:
                doc = _per_os_doc_url(tool)
                items.append(
                    _ToolPlanItem(
                        tool=tool,
                        artifact=None,
                        skip_reason=(
                            f"vendor — install manually: "
                            f"{doc or '(see family manifest)'}"
                        ),
                    )
                )
                continue
            try:
                adapter = _ts.adapter_for(tool.source)
                artifact = adapter.resolve(tool, host)
            except FamilyToolchainInstallerUnsupportedHostError as exc:
                warnings.append(str(exc))
                items.append(
                    _ToolPlanItem(
                        tool=tool,
                        artifact=None,
                        skip_reason=f"unsupported host — {exc}",
                    )
                )
                continue
            except FamilyToolchainInstallerError as exc:
                raise click.ClickException(str(exc)) from exc
            items.append(_ToolPlanItem(tool=tool, artifact=artifact, skip_reason=""))
    return items, warnings


_OS_DOC_KEYS: dict[str, str] = {
    "Darwin": "macos",
    "Linux": "linux",
    "Windows": "windows",
}


def _per_os_doc_url(tool: ToolRequirement) -> str | None:
    """Best per-OS install_docs URL for a vendor tool."""
    docs = tool.install_docs or {}
    if not docs:
        return None
    os_key = _OS_DOC_KEYS.get(platform.system())
    if os_key and os_key in docs:
        return docs[os_key]
    return next(iter(docs.values()), None)


# ---------------------------------------------------------------------------
# Lockfile helpers
# ---------------------------------------------------------------------------


def _lockfile_path(project_dir: Path) -> Path:
    return AlloyDir(root=project_dir).base / _lockfile.LOCKFILE_NAME


def _read_lock(project_dir: Path) -> _lockfile.ToolchainLock:
    path = _lockfile_path(project_dir)
    existing = _lockfile.read_optional(path)
    return existing if existing is not None else _lockfile.empty()


def _write_lock(project_dir: Path, lock: _lockfile.ToolchainLock) -> Path:
    path = _lockfile_path(project_dir)
    _lockfile.write(path, lock)
    return path


# ---------------------------------------------------------------------------
# alloy toolchain
# ---------------------------------------------------------------------------


@click.group("toolchain", help="Manage the per-family binary toolchain store.")
def toolchain_command() -> None:
    """Wave-2 verbs for the content-addressed toolchain store."""


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


@toolchain_command.command(
    "install",
    help="Download + verify + extract every non-vendor tool the family declares.",
)
@click.option(
    "--for",
    "family_override",
    metavar="FAMILY",
    default=None,
    callback=_validate_family,
    help="MCU family id (default: resolved from the project's alloy.toml).",
)
@click.option(
    "--shared",
    is_flag=True,
    default=False,
    help="Install only into the global store; do NOT update the project lockfile.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the plan + estimated total size without writing anything.",
)
@click.option(
    "--include-optional",
    is_flag=True,
    default=False,
    help="Also install the family's optional tools.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-download even when the SHA matches an already-installed entry.",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root (used for family resolution + lockfile updates).",
)
def install_command(
    family_override: str | None,
    shared: bool,
    dry_run: bool,
    include_optional: bool,
    force: bool,
    project_dir: Path,
) -> None:
    project_dir = project_dir.resolve()
    console = Console()

    try:
        manifest = _resolve_family_or_exit(project_dir, family_override)
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    plan, warnings = _plan_for_family(manifest, include_optional=include_optional)

    actionable = [item for item in plan if item.artifact is not None]
    skipped = [item for item in plan if item.artifact is None]

    # Dry-run: print the plan + estimated size, write nothing.
    if dry_run:
        _render_install_plan(console, manifest, plan)
        total_bytes = sum(
            (item.artifact.size_bytes or 0)
            for item in actionable
            if item.artifact is not None
        )
        console.print(
            f"\n[bold]Total estimated download:[/bold] "
            f"{_human_bytes(total_bytes)} across {len(actionable)} tool(s).  "
            f"{len(skipped)} skipped (vendor/unsupported)."
        )
        for warning in warnings:
            console.print(f"[yellow]warning:[/yellow] {warning}")
        return

    # Live install path
    console.print(
        f"[bold]Installing toolchain for {manifest.family_id}[/bold] "
        f"({len(actionable)} tools to fetch, {len(skipped)} skipped)"
    )
    for warning in warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")

    lock = _read_lock(project_dir)
    install_outcomes: list[_manager.InstallOutcome] = []
    for item in plan:
        if item.artifact is None:
            console.print(
                f"  [yellow]✗ {item.tool.tool} skipped ({item.skip_reason})[/yellow]"
            )
            continue
        try:
            outcome = _manager.install(
                item.artifact,
                force=force,
                on_line=lambda line: console.print(line, highlight=False),
            )
        except AlloyCliError as exc:
            raise click.ClickException(str(exc)) from exc
        install_outcomes.append(outcome)
        if not shared:
            lock = _lockfile.add(
                lock,
                item.artifact.tool,
                item.artifact.version,
                item.artifact.sha256,
            )

    if not shared and install_outcomes:
        lock_path = _write_lock(project_dir, lock)
        console.print(
            f"\n[green]✓ Updated[/green] {lock_path.relative_to(project_dir)} "
            f"with {len(install_outcomes)} pin(s)."
        )

    total_downloaded = sum(o.bytes_downloaded for o in install_outcomes)
    console.print(
        f"\n[bold green]✓ Done.[/bold green] {len(install_outcomes)} tool(s) "
        f"installed, {_human_bytes(total_downloaded)} downloaded."
    )


def _render_install_plan(
    console: Console, manifest: FamilyManifest, plan: list[_ToolPlanItem]
) -> None:
    table = Table(
        title=f"alloy toolchain install --for {manifest.family_id} (dry-run)",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("tool")
    table.add_column("version")
    table.add_column("source")
    table.add_column("status")
    table.add_column("size", justify="right")
    table.add_column("url / hint")
    for item in plan:
        if item.artifact is not None:
            size = _human_bytes(item.artifact.size_bytes or 0) if item.artifact.size_bytes else "?"
            table.add_row(
                item.tool.tool,
                item.artifact.version,
                item.artifact.source,
                "[green]install[/green]",
                size,
                item.artifact.url,
            )
        else:
            table.add_row(
                item.tool.tool,
                item.tool.version,
                item.tool.source,
                "[yellow]skip[/yellow]",
                "-",
                f"[dim]{item.skip_reason}[/dim]",
            )
    console.print(table)


def _human_bytes(n: int) -> str:
    if n <= 0:
        return "?"
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n //= 1024  # type: ignore[assignment]
    return f"{n} B"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@toolchain_command.command(
    "list", help="Show the per-family tool list with install state."
)
@click.option(
    "--for",
    "family_override",
    metavar="FAMILY",
    default=None,
    callback=_validate_family,
)
@click.option(
    "--installed",
    "filter_installed",
    is_flag=True,
    default=False,
    help="Show only tools that are installed.",
)
@click.option(
    "--missing",
    "filter_missing",
    is_flag=True,
    default=False,
    help="Show only tools that are not installed.",
)
@click.option(
    "--include-optional",
    is_flag=True,
    default=False,
    help="Include the family's optional tools in the listing.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Emit JSON.")
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
)
def list_command(
    family_override: str | None,
    filter_installed: bool,
    filter_missing: bool,
    include_optional: bool,
    as_json: bool,
    project_dir: Path,
) -> None:
    project_dir = project_dir.resolve()
    if filter_installed and filter_missing:
        raise click.UsageError(
            "--installed and --missing are mutually exclusive."
        )

    manifest = _resolve_family_or_exit(project_dir, family_override)
    rows = _list_rows(manifest, include_optional=include_optional)

    if filter_installed:
        rows = [r for r in rows if r["state"] == "installed"]
    elif filter_missing:
        rows = [r for r in rows if r["state"] in {"missing", "vendor"}]

    if as_json:
        payload = {
            "family_id": manifest.family_id,
            "host": str(_ts.host_triple()),
            "tools": rows,
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return

    _render_list_table(Console(), manifest, rows)


def _list_rows(
    manifest: FamilyManifest, *, include_optional: bool
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    tiers: list[tuple[str, tuple[ToolRequirement, ...]]] = [
        ("required", manifest.required),
        ("recommended", manifest.recommended),
    ]
    if include_optional:
        tiers.append(("optional", manifest.optional))

    for tier_name, tools in tiers:
        for tool in tools:
            if tool.is_vendor:
                rows.append(
                    {
                        "tool": tool.tool,
                        "version": tool.version,
                        "source": tool.source,
                        "tier": tier_name,
                        "state": "vendor",
                        "installed_path": None,
                        "installed_version": None,
                        "size_bytes": None,
                    }
                )
                continue
            installed = _manager.find_installed(tool.tool)
            if installed is None:
                rows.append(
                    {
                        "tool": tool.tool,
                        "version": tool.version,
                        "source": tool.source,
                        "tier": tier_name,
                        "state": "missing",
                        "installed_path": None,
                        "installed_version": None,
                        "size_bytes": None,
                    }
                )
            else:
                rows.append(
                    {
                        "tool": tool.tool,
                        "version": tool.version,
                        "source": tool.source,
                        "tier": tier_name,
                        "state": "installed",
                        "installed_path": str(installed.absolute_primary()),
                        "installed_version": installed.version,
                        "size_bytes": _dir_size(installed.store_path),
                    }
                )
    return rows


def _dir_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _render_list_table(
    console: Console, manifest: FamilyManifest, rows: list[dict[str, Any]]
) -> None:
    table = Table(
        title=f"alloy toolchain list --for {manifest.family_id}",
        show_lines=False,
        header_style="bold magenta",
    )
    table.add_column("tool")
    table.add_column("tier")
    table.add_column("state")
    table.add_column("version")
    table.add_column("source")
    table.add_column("size", justify="right")
    for row in rows:
        state = row["state"]
        if state == "installed":
            colour = "[green]✓ installed[/green]"
        elif state == "vendor":
            colour = "[yellow]vendor[/yellow]"
        else:
            colour = "[red]✗ missing[/red]"
        size = (
            _human_bytes(row["size_bytes"]) if row.get("size_bytes") else "-"
        )
        version = row.get("installed_version") or row["version"]
        table.add_row(
            row["tool"],
            row["tier"],
            colour,
            version,
            row["source"],
            size,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# use
# ---------------------------------------------------------------------------


@toolchain_command.command(
    "use", help="Pin a specific tool version in .alloy/toolchain.lock."
)
@click.argument("spec", metavar="TOOL@VERSION")
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
)
def use_command(spec: str, project_dir: Path) -> None:
    project_dir = project_dir.resolve()
    if "@" not in spec:
        raise click.BadParameter(
            f"Expected TOOL@VERSION, got {spec!r}.",
            param_hint="SPEC",
        )
    tool, version = spec.split("@", 1)
    if not tool or not version:
        raise click.BadParameter(
            f"Both TOOL and VERSION must be non-empty (got {spec!r}).",
            param_hint="SPEC",
        )

    sha = _resolve_sha_from_pins(tool, version)
    if sha is None:
        available = _versions_for_tool(tool)
        if not available:
            raise click.ClickException(
                f"No pin file ships {tool!r}.  Known tools: "
                f"{', '.join(sorted(_known_pinned_tools())) or '(none)'}."
            )
        raise click.ClickException(
            f"No pin for {tool}@{version} on {_ts.host_triple()}.  "
            f"Available: {', '.join(available)}."
        )

    lock = _read_lock(project_dir)
    lock = _lockfile.add(lock, tool, version, sha)
    lock_path = _write_lock(project_dir, lock)
    console = Console()
    rel = lock_path.relative_to(project_dir) if lock_path.is_relative_to(project_dir) else lock_path
    console.print(
        f"[green]✓ Pinned[/green] {tool}@{version} (sha={sha[:12]}...) "
        f"in {rel}."
    )


def _resolve_sha_from_pins(tool: str, version: str) -> str | None:
    """Walk every shipped pin file and find the SHA for the active host."""
    host = str(_ts.host_triple())
    for kind in _ts.known_source_kinds():
        try:
            payload = _ts._load_pins(kind)
        except AlloyCliError:
            continue
        for entry in payload.get("tools") or ():
            if not isinstance(entry, dict):
                continue
            if entry.get("tool") != tool:
                continue
            if entry.get("version") != version:
                continue
            host_payload = (entry.get("hosts") or {}).get(host)
            if isinstance(host_payload, dict):
                sha = host_payload.get("sha256")
                if isinstance(sha, str):
                    return sha
    return None


def _versions_for_tool(tool: str) -> list[str]:
    out: list[str] = []
    for kind in _ts.known_source_kinds():
        try:
            payload = _ts._load_pins(kind)
        except AlloyCliError:
            continue
        for entry in payload.get("tools") or ():
            if isinstance(entry, dict) and entry.get("tool") == tool:
                version = entry.get("version")
                if isinstance(version, str):
                    out.append(version)
    return sorted(set(out))


def _known_pinned_tools() -> set[str]:
    out: set[str] = set()
    for kind in _ts.known_source_kinds():
        try:
            payload = _ts._load_pins(kind)
        except AlloyCliError:
            continue
        for entry in payload.get("tools") or ():
            if isinstance(entry, dict) and isinstance(entry.get("tool"), str):
                out.add(entry["tool"])
    return out


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


@toolchain_command.command(
    "prune", help="Garbage-collect store entries no project lockfile pins."
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="List candidates without deleting.",
)
@click.option(
    "--projects-root",
    "projects_roots",
    multiple=True,
    type=click.Path(file_okay=False, path_type=Path),
    help=(
        "One or more directories to scan recursively for "
        "`.alloy/toolchain.lock` files.  Repeat to add more.  Default: "
        "the current --project-dir only."
    ),
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
)
def prune_command(
    dry_run: bool, projects_roots: tuple[Path, ...], project_dir: Path
) -> None:
    project_dir = project_dir.resolve()
    pinning_projects = _discover_projects(project_dir, projects_roots)
    report = _manager.prune(projects=pinning_projects, dry_run=dry_run)

    console = Console()
    if not report.candidates:
        console.print("[green]✓ Store is clean.[/green]  Nothing to prune.")
        return

    table = Table(show_lines=False, header_style="bold magenta")
    table.add_column("tool")
    table.add_column("version")
    table.add_column("sha (short)")
    table.add_column("size", justify="right")
    table.add_column("status")
    for cand in report.candidates:
        was_deleted = cand in report.deleted
        status = (
            "[green]deleted[/green]"
            if was_deleted
            else ("[yellow]would delete[/yellow]" if dry_run else "[red]kept (?)[/red]")
        )
        table.add_row(
            cand.tool,
            cand.version,
            cand.sha256[:12] + "...",
            _human_bytes(cand.size_bytes),
            status,
        )
    console.print(table)
    if dry_run:
        total = sum(c.size_bytes for c in report.candidates)
        console.print(
            f"\n[dim]--dry-run: nothing deleted.  Run without --dry-run to "
            f"reclaim ~{_human_bytes(total)}.[/dim]"
        )
    else:
        console.print(
            f"\n[bold green]✓ Pruned[/bold green] {len(report.deleted)} entry/ies, "
            f"{_human_bytes(report.bytes_freed)} reclaimed."
        )


def _discover_projects(
    project_dir: Path, roots: Sequence[Path]
) -> tuple[Path, ...]:
    """Build the project-list `prune` consults.

    When ``roots`` is empty, we use the current ``--project-dir`` if it
    has a lockfile, else nothing.  When ``roots`` is provided, walk
    each one looking for `.alloy/toolchain.lock` files and return the
    set of project roots.
    """
    if not roots:
        if (project_dir / ".alloy" / _lockfile.LOCKFILE_NAME).exists():
            return (project_dir,)
        return ()
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for lock in root.rglob(f".alloy/{_lockfile.LOCKFILE_NAME}"):
            project_root = lock.parent.parent.resolve()
            if project_root in seen:
                continue
            seen.add(project_root)
            out.append(project_root)
    return tuple(out)


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------


@toolchain_command.command(
    "shell",
    help="Spawn a subshell with PATH augmented for cached toolchain binaries.",
)
@click.option(
    "--for",
    "family_override",
    metavar="FAMILY",
    default=None,
    callback=_validate_family,
)
@click.option(
    "--print-path",
    "print_only",
    is_flag=True,
    default=False,
    help="Print the augmented PATH instead of spawning a subshell.",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
)
def shell_command(
    family_override: str | None, print_only: bool, project_dir: Path
) -> None:
    project_dir = project_dir.resolve()
    # Family is optional for `shell` — even without one, we can show
    # whatever's currently in the store.  But the shell verb is most
    # useful with a family scoping, so we still try.
    if family_override is not None or (project_dir / PROJECT_FILE).exists():
        try:
            _resolve_family_or_exit(project_dir, family_override)
        except click.ClickException:
            # Allow shell with no family — falls back to "everything in
            # the store".
            pass

    bin_dirs = _manager.installed_bin_dirs()
    if not bin_dirs:
        raise click.ClickException(
            "No toolchain binaries installed.  Run "
            "`alloy toolchain install --for <family>` first."
        )

    augmented = os.pathsep.join(str(p) for p in bin_dirs)
    existing = os.environ.get("PATH", "")
    new_path = augmented + (os.pathsep + existing if existing else "")

    if print_only:
        click.echo(new_path)
        return

    env = dict(os.environ)
    env["PATH"] = new_path
    env.setdefault("ALLOY_TOOLCHAIN_SHELL", "1")  # marker for the spawned shell

    console = Console()
    console.print(
        f"[bold]Entering alloy toolchain shell[/bold] "
        f"({len(bin_dirs)} bin dir(s) prepended to PATH)."
    )
    console.print(
        "[dim]Type 'exit' or Ctrl-D to return to your normal shell.[/dim]"
    )

    if sys.platform == "win32":
        cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/K"]
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
        cmd = [shell, "-i"]

    raise SystemExit(subprocess.call(cmd, env=env))


__all__ = ["toolchain_command"]
