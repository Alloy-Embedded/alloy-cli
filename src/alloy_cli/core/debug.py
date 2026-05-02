"""``alloy debug`` orchestration.

Spawns a probe-rs gdb-server in the background, then attaches the
user's GDB front-end.  The Click wrapper in
:mod:`alloy_cli.commands.debug` owns process lifetime; the helpers
here stay test-friendly (no real subprocess unless the caller asks
for it).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core.errors import AlloyCliError, ToolchainMissingError


class GdbNotFoundError(AlloyCliError):
    error_type = "gdb-not-found"


@dataclass(frozen=True, slots=True)
class DebugSession:
    """Result of :func:`build_invocation`.

    The actual process management happens in
    :mod:`alloy_cli.commands.debug`, which uses :class:`subprocess.Popen`
    directly so it can attach interactively.  This dataclass is the
    *plan*: every command that needs to be launched + its arguments.
    """

    server_args: tuple[str, ...]
    gdb_args: tuple[str, ...]
    elf: Path
    gdb_port: int = 1337


def _resolve_gdb(explicit: str | None = None, *, require: bool = True) -> str:
    """Pick a GDB binary from ``--gdb-ui`` / env / PATH.

    ``require=False`` skips the on-PATH check (used by tests / dry-run).
    """
    if explicit:
        if require and shutil.which(explicit) is None:
            raise GdbNotFoundError(
                f"GDB front-end {explicit!r} not found on PATH.  "
                "Set --gdb-ui to a full path or install it."
            )
        return explicit
    env_gdb = os.environ.get("ALLOY_GDB")
    if env_gdb:
        return env_gdb
    if not require:
        return "arm-none-eabi-gdb"
    for candidate in ("arm-none-eabi-gdb", "gdb-multiarch", "gdb"):
        if shutil.which(candidate) is not None:
            return candidate
    raise GdbNotFoundError("No GDB front-end found.  Install arm-none-eabi-gdb or set ALLOY_GDB.")


def build_invocation(
    *,
    elf: Path,
    chip: str,
    gdb_ui: str | None = None,
    probe_kind: str = "auto",
    gdb_port: int = 1337,
    require_toolchain: bool = True,
) -> DebugSession:
    """Compose the (server_args, gdb_args) pair without spawning anything yet."""
    if require_toolchain:
        status = _toolchain.detect_probe_rs()
        if not status.present:
            raise ToolchainMissingError(
                f"probe-rs is required for `alloy debug`.  Install: {status.install_hint}"
            )

    server_args: list[str] = [
        "probe-rs",
        "gdb",
        "--chip",
        chip,
        "--gdb-connection-string",
        f"127.0.0.1:{gdb_port}",
        str(elf),
    ]
    if probe_kind != "auto":
        server_args.extend(["--probe", probe_kind])

    gdb_binary = _resolve_gdb(gdb_ui, require=require_toolchain)
    gdb_args: list[str] = [
        gdb_binary,
        "-ex",
        f"target extended-remote :{gdb_port}",
        "-ex",
        f"file {elf}",
        "-ex",
        "load",
        "-ex",
        "tbreak main",
        "-ex",
        "continue",
    ]

    return DebugSession(
        server_args=tuple(server_args),
        gdb_args=tuple(gdb_args),
        elf=elf,
        gdb_port=gdb_port,
    )


__all__ = ["DebugSession", "GdbNotFoundError", "build_invocation"]
