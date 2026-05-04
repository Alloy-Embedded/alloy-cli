"""``alloy monitor`` — live UART / RTT log viewer (Wave 4 group 4).

Streams bytes from the target's debug UART (or RTT channel) to
stdout.  Press ``Ctrl+]`` to disconnect cleanly; the command
reports byte count, duration, and last line on close.

Auto-detects the debug UART from ``alloy.toml``'s peripheral list
when the project declares a console UART (kind=uart, name=console
or similar).  ``--port`` always overrides; ``--baud`` overrides
the detected baud or falls back to 115200.

Modes:
- ``--mode raw`` (default) — opens ``--port`` directly via PySerial.
- ``--mode rtt``           — dispatches through the lockfile-pinned
                              probe-rs RTT channel (Wave-4 read-only;
                              full duplex is Wave-5).

The orchestrator's ``open_monitor`` is the seam.  Tests inject a
``FakeProbe`` so the entire flow can be exercised without real
hardware.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

import click
from rich.console import Console

from alloy_cli.core import boards as _boards
from alloy_cli.core import probe_orchestrator as _po
from alloy_cli.core.errors import (
    AlloyCliError,
    BoardNotFoundError,
    FamilyToolchainProbeError,
    ProbeOperationCancelledError,
)
from alloy_cli.core.project import PROJECT_FILE, ProjectConfig, read


def _resolve_debug_uart_baud(config: ProjectConfig) -> int | None:
    """Best-effort: find the project's debug UART baud rate from alloy.toml.

    Checks (in order):
    1. Peripheral with ``kind=="uart"`` and name in ``{"console","debug","uart_debug"}``.
    2. ``board.json`` ``uart.debug.baud`` field for the board declared in alloy.toml.

    Returns ``None`` when nothing resolves; the caller falls back to 115200.
    """
    for peripheral in config.peripherals:
        if peripheral.kind != "uart":
            continue
        if peripheral.name not in ("console", "debug", "uart_debug"):
            continue
        baud = peripheral.payload.get("baud") if peripheral.payload else None
        if isinstance(baud, int):
            return baud

    # Try board.json uart.debug.baud as a second source.
    if config.board is not None:
        try:
            manifest = _boards.lookup(config.board.id)
            baud = manifest.payload.get("uart", {}).get("debug", {}).get("baud")
            if isinstance(baud, int):
                return baud
        except (BoardNotFoundError, Exception):
            pass

    return None


def _autodetect_port(config: ProjectConfig | None, console: Console) -> Path | None:
    """Scan the host's USB serial devices and return the best match.

    Requires a board context: ``config.board.id`` must resolve to a
    ``board.json`` that declares ``serial_globs``.  Without that context
    the function returns ``None`` so the caller can surface a clear
    ``--port`` hint.  This avoids accidentally opening an unrelated serial
    device on developer machines with many adapters attached.

    Strategy (when board context is available):
    1. Load ``serial_globs`` from the board's ``board.json``.
    2. List all ports via ``serial.tools.list_ports.comports()``.
    3. Return the single port whose device path matches any glob.
    4. If multiple match → pick the first and print a disambiguation note.
    5. If none match → return ``None``.

    ``--port`` always overrides this function (the caller never calls it
    when the flag is set).
    """
    # No board context → require explicit --port.
    if config is None or config.board is None:
        return None

    try:
        manifest = _boards.lookup(config.board.id)
        globs: list[str] = manifest.payload.get("serial_globs", []) or []
    except (BoardNotFoundError, Exception):
        return None

    if not globs:
        return None

    try:
        from serial.tools import list_ports  # pyserial
    except ImportError:
        return None

    usb_ports = [
        p for p in list_ports.comports()
        if "Bluetooth" not in (p.description or "")
    ]
    matched = [
        p for p in usb_ports
        if any(fnmatch.fnmatch(p.device, g) for g in globs)
    ]

    if not matched:
        return None

    port = Path(matched[0].device)
    desc = matched[0].description or matched[0].device

    if len(matched) == 1:
        console.print(f"[dim]Auto-detected port:[/dim] [cyan]{port}[/cyan] [dim]({desc})[/dim]")
    else:
        names = ", ".join(p.device for p in matched)
        console.print(
            f"[dim]Auto-detected port:[/dim] [cyan]{port}[/cyan] "
            f"[dim](multiple matched: {names} — pass --port to override)[/dim]"
        )
    return port


def _read_project_config(project_dir: Path) -> ProjectConfig | None:
    toml = project_dir / PROJECT_FILE
    if not toml.exists():
        return None
    try:
        return read(toml)
    except AlloyCliError:
        return None


def _render_probe_error(exc: FamilyToolchainProbeError) -> str:
    cookbook = f"docs/ERROR_COOKBOOK.md#{exc.error_type}"
    return f"{exc}\n  See {cookbook} for recovery steps."


@click.command(
    "monitor",
    help=(
        "Stream bytes from the target's debug UART (or RTT channel) "
        "to stdout.  Press Ctrl+] to disconnect cleanly.  Resolves "
        "the port from alloy.toml when the project declares a "
        "console UART; --port / --baud overrides."
    ),
)
@click.option(
    "--port",
    "port",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Serial device path (e.g. /dev/cu.usbmodem1234).  Overrides autodetect.",
)
@click.option(
    "--baud",
    "baud",
    type=int,
    default=None,
    help=(
        "Baud rate.  Overrides the project's [uart].debug config; "
        "falls back to 115200 when neither resolves."
    ),
)
@click.option(
    "--mode",
    "mode",
    type=click.Choice(["raw", "rtt"], case_sensitive=False),
    default="raw",
    show_default=True,
    help="Stream source: raw UART bytes or probe-rs RTT channel.",
)
@click.option(
    "--ansi/--no-ansi",
    "ansi",
    default=False,
    show_default=True,
    help=(
        "Pass through ANSI escape sequences.  Default strips them so the log stays grep-friendly."
    ),
)
@click.option(
    "--probe",
    "probe_hint",
    metavar="VID:PID:SERIAL",
    default=None,
    help="Probe selector (only meaningful in --mode rtt).",
)
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Project root containing alloy.toml + .alloy/toolchain.lock.",
)
def monitor_command(
    port: Path | None,
    baud: int | None,
    mode: str,
    ansi: bool,
    probe_hint: str | None,
    project_dir: Path,
) -> None:
    """Open a streaming monitor session."""
    project_dir = project_dir.resolve()
    console = Console()

    # ---- Port + baud resolution ----
    config = _read_project_config(project_dir)
    project_baud: int | None = None
    if config is not None:
        project_baud = _resolve_debug_uart_baud(config)

    final_port: Path | None = port
    final_baud: int = baud if baud is not None else (project_baud or 115200)

    if final_port is None and mode == "raw":
        final_port = _autodetect_port(config, console)
        if final_port is None:
            raise click.ClickException(
                "No serial port found.  Connect your board and retry, "
                "or pass --port <path> explicitly.\n"
                "  Auto-detect requires a [board] id in alloy.toml with "
                "serial_globs declared in board.json.\n"
                "  List ports: python3 -m serial.tools.list_ports"
            )

    # ---- Probe selection (only meaningful in RTT mode) ----
    probe: _po.Probe
    if mode == "rtt":
        try:
            identity = _po.select_probe(hint=probe_hint, project_root=project_dir)
        except FamilyToolchainProbeError as exc:
            raise click.ClickException(_render_probe_error(exc)) from exc
        except AlloyCliError as exc:
            raise click.ClickException(str(exc)) from exc
        probe = _po.real_probe_for(identity, project_root=project_dir)
    else:
        # Raw UART: we still go through the orchestrator surface so
        # the cancellation contract + summary line stays uniform.  A
        # synthetic ProbeIdentity is fine — the backend reads only
        # the port/baud.
        probe = _po.real_probe_for(
            _po.ProbeIdentity(
                vid="0000",
                pid="0000",
                serial="",
                kind="serial",
                vendor_only=False,
            ),
            project_root=project_dir,
        )

    console.print(
        f"[dim]Connecting to[/dim] [cyan]{final_port}[/cyan] "
        f"[dim]@[/dim] [cyan]{final_baud}[/cyan] "
        f"[dim](mode={mode}, press Ctrl+] to exit)[/dim]"
    )

    # ---- Streaming session ----
    last_line: list[str] = []  # mutable so the on_event callback can update

    def _on_event(event: _po.MonitorEvent) -> None:
        if isinstance(event, _po.MonitorOpened):
            return  # banner already printed
        if isinstance(event, _po.MonitorBytes):
            decoded = event.chunk.decode("utf-8", errors="replace")
            if not ansi:
                # Cheap ANSI-CSI strip so the log stays grep-friendly.
                import re

                decoded = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", decoded)
            sys.stdout.write(decoded)
            sys.stdout.flush()
            if "\n" in decoded:
                last_line.append(decoded.rsplit("\n", 1)[0].rsplit("\n", 1)[-1].strip())
        if isinstance(event, _po.MonitorClosed):
            # The orchestrator may emit this via the backend; the CLI
            # still catches ProbeOperationCancelledError below for the
            # Ctrl+] path.
            pass

    try:
        _po.open_monitor(
            probe,
            port=final_port,
            baud=final_baud,
            mode=mode,
            on_event=_on_event,
        )
    except ProbeOperationCancelledError as exc:
        # Graceful Ctrl+] disconnect → print the summary line + exit 0.
        summary = (
            f"\n[dim]Closed monitor session.  "
            f"{exc.bytes_captured} bytes captured over "
            f"{exc.duration_ms / 1000:.1f}s.[/dim]"
        )
        if exc.last_line:
            summary += f"\n[dim]Last line: {exc.last_line!r}[/dim]"
        console.print(summary)
        return
    except KeyboardInterrupt:  # pragma: no cover — SIGINT path
        console.print("\n[dim]Closed monitor session (interrupted).[/dim]")
        return
    except AlloyCliError as exc:
        raise click.ClickException(str(exc)) from exc

    # Fall-through: backend returned without raising — finite session
    # (e.g. test fixture).  Print a minimal summary.
    console.print(
        f"\n[dim]Monitor session ended.  Last line: {last_line[-1]!r}[/dim]"
        if last_line
        else "\n[dim]Monitor session ended.[/dim]"
    )


__all__ = ["monitor_command"]
