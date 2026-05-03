"""``alloy reset`` — non-destructive target reset (Wave 4 of toolchain-management).

Issues a CPU or hardware reset of the connected probe target.
Dispatches through :func:`alloy_cli.core.probe_orchestrator.
reset_target` so the same probe-selection + binary-resolution
pipeline ``alloy flash`` and the future ``alloy debug`` use lands
here too.

Flag matrix:

- ``--soft`` (default) → CPU reset via probe-rs's ``reset`` verb.
- ``--hard``           → pulses nRST line via
                         ``--connect-under-reset``.  Mutex with
                         ``--soft``.
- ``--halt-after-reset`` → leaves the core halted post-reset so
                           a debugger can attach.
- ``--probe vid:pid:serial`` → explicit probe selector.  Matches
                                ``alloy flash --probe`` semantics.
- ``--project-dir <path>`` → defaults to CWD; used to resolve
                              ``.alloy/toolchain.lock`` for the
                              probe-rs binary.

Errors map to typed envelopes (`family-toolchain-probe-{not-attached,
multiple-attached, unauthorised, not-found}`) with cookbook links.
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import (
    AlloyCliError,
    FamilyToolchainEraseProbeFailedError,
    FamilyToolchainProbeError,
)


def _format_probe_label(probe: _po.ProbeIdentity) -> str:
    """Render the probe identity for the next-step panel."""
    serial_part = f" sn={probe.serial}" if probe.serial else ""
    return f"{probe.kind}{serial_part} ({probe.vid}:{probe.pid})"


@click.command(
    "reset",
    help=(
        "Reset the connected probe target.  Default is a soft CPU reset; "
        "pass --hard to pulse nRST.  Lockfile-aware: the probe-rs binary "
        "comes from .alloy/toolchain.lock when present."
    ),
)
@click.option(
    "--soft/--hard",
    "soft",
    default=True,
    show_default=True,
    help="Reset method: --soft (CPU reset, default) or --hard (nRST line).",
)
@click.option(
    "--halt-after-reset",
    is_flag=True,
    default=False,
    help="Leave the core halted after reset so a debugger can attach.",
)
@click.option(
    "--probe",
    "probe_hint",
    metavar="VID:PID:SERIAL",
    default=None,
    help=(
        "Explicit probe selector (matches alloy flash --probe).  Each "
        "field is optional — '0483' matches every ST-Link, "
        "'0483:374b' matches every ST-Link/V2-1, the full triple "
        "pinpoints one probe."
    ),
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing .alloy/toolchain.lock.",
)
def reset_command(
    soft: bool,
    halt_after_reset: bool,
    probe_hint: str | None,
    project_dir: Path,
) -> None:
    """Reset the connected target via the lockfile-pinned probe-rs."""
    project_dir = project_dir.resolve()
    console = Console()

    method = "soft" if soft else "hard"

    try:
        identity = _po.select_probe(hint=probe_hint, project_root=project_dir)
    except FamilyToolchainProbeError as exc:
        raise click.ClickException(_render_probe_error(exc)) from exc
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    probe = _po.real_probe_for(identity, project_root=project_dir)

    try:
        report = _po.reset_target(probe, method=method, halt_after=halt_after_reset)
    except FamilyToolchainEraseProbeFailedError as exc:
        # Wave-4 group 1 reuses the erase-probe-failed error type for
        # any backend-side dispatch failure during reset.  The cookbook
        # documents both contexts.
        raise click.ClickException(
            f"Reset failed via probe-rs (returncode={exc.returncode}):\n"
            f"  {exc.stderr.strip() or str(exc)}"
        ) from exc
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    panel_body = (
        f"[bold green]✓ Target reset.[/bold green]\n\n"
        f"Probe:    [cyan]{_format_probe_label(report.probe)}[/cyan]\n"
        f"Method:   [cyan]{report.method}[/cyan]"
        f"{'  (halted after reset)' if report.halt_after else ''}\n"
        f"Duration: [cyan]{report.duration_ms} ms[/cyan]"
    )
    console.print(Panel.fit(panel_body, border_style="cyan", title="alloy reset"))


def _render_probe_error(exc: FamilyToolchainProbeError) -> str:
    """Render a typed probe error with a cookbook link."""
    cookbook = (
        f"docs/ERROR_COOKBOOK.md#{exc.error_type}"
        if exc.error_type.startswith("family-toolchain-probe-")
        else "docs/ERROR_COOKBOOK.md"
    )
    suffix = f"\n  See {cookbook} for recovery steps."

    if exc.error_type == "family-toolchain-probe-multiple-attached":
        from alloy_cli.core.errors import FamilyToolchainProbeMultipleAttachedError

        if isinstance(exc, FamilyToolchainProbeMultipleAttachedError) and exc.detected:
            listing = "\n".join(
                f"    • {kind} {vid}:{pid}:{serial}" for vid, pid, serial, kind in exc.detected
            )
            return f"{exc}\n\nDetected probes:\n{listing}{suffix}"
    if exc.error_type == "family-toolchain-probe-unauthorised":
        from alloy_cli.core.errors import FamilyToolchainProbeUnauthorisedError

        if isinstance(exc, FamilyToolchainProbeUnauthorisedError):
            extra = f"  Use {exc.vendor_tool!r} manually."
            if exc.install_doc_url:
                extra += f"\n  Download: {exc.install_doc_url}"
            return f"{exc}\n\n{extra}{suffix}"
    return f"{exc}{suffix}"


__all__ = ["reset_command"]
