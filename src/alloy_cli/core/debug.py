"""``alloy debug`` orchestration.

Spawns a probe-rs gdb-server in the background, then attaches the
user's GDB front-end.  The Click wrapper in
:mod:`alloy_cli.commands.debug` owns process lifetime; the helpers
here stay test-friendly (no real subprocess unless the caller asks
for it).

Wave 2: when the project carries ``.alloy/toolchain.lock``, both
the gdb-server (``probe-rs gdb``) and the gdb front-end resolve to
absolute paths in the content-addressed store.  Legacy projects
without a lockfile keep using PATH-resolved binaries.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core.errors import AlloyCliError, ToolchainMissingError

# Known gdb binary names across our supported architectures.  Wave-2's
# lockfile resolution walks this set in order; the first match wins.
KNOWN_GDB_BINARIES: tuple[str, ...] = (
    "arm-none-eabi-gdb",
    "xtensa-esp-elf-gdb",
    "xtensa-esp32-elf-gdb",
    "riscv32-esp-elf-gdb",
    "riscv-none-elf-gdb",
    "gdb-multiarch",
)


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


def _resolve_gdb_via_lockfile(project_root: Path | None) -> str | None:
    """Walk ``KNOWN_GDB_BINARIES`` against the project lockfile.

    Returns the absolute path to the first gdb binary the lockfile
    pins (directly OR via a bundle), or ``None`` when no project
    root or no lockfile pins any of them.
    """
    if project_root is None:
        return None
    from alloy_cli.core import toolchain_manager as _tm

    for name in KNOWN_GDB_BINARIES:
        path = _tm.resolve_for_lockfile(project_root, name)
        if path is not None:
            return str(path)
    return None


def _resolve_probe_rs_via_lockfile(project_root: Path | None) -> str | None:
    """Mirror of :func:`_resolve_gdb_via_lockfile` for ``probe-rs``."""
    if project_root is None:
        return None
    from alloy_cli.core import toolchain_manager as _tm

    path = _tm.resolve_for_lockfile(project_root, "probe-rs")
    return str(path) if path is not None else None


def _resolve_gdb(
    explicit: str | None = None,
    *,
    require: bool = True,
    project_root: Path | None = None,
) -> str:
    """Pick a GDB binary from explicit override / lockfile / env / PATH.

    Resolution priority:
      1. ``explicit`` (e.g. ``--gdb-ui``) — verbatim, must exist on
         PATH when ``require=True``.
      2. The project's ``.alloy/toolchain.lock`` (when ``project_root``
         is provided and pins a known gdb binary directly or via a
         bundled binary list).
      3. ``ALLOY_GDB`` environment variable.
      4. PATH-discovered ``arm-none-eabi-gdb`` / ``gdb-multiarch`` /
         ``gdb``.

    ``require=False`` skips the on-PATH check (used by tests + dry-run).
    """
    if explicit:
        if require and shutil.which(explicit) is None:
            raise GdbNotFoundError(
                f"GDB front-end {explicit!r} not found on PATH.  "
                "Set --gdb-ui to a full path or install it."
            )
        return explicit

    pinned = _resolve_gdb_via_lockfile(project_root)
    if pinned is not None:
        return pinned

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
    project_root: Path | None = None,
) -> DebugSession:
    """Compose the (server_args, gdb_args) pair without spawning anything yet.

    ``project_root`` opts into Wave-2 lockfile resolution: when set
    and the project has ``.alloy/toolchain.lock``, both probe-rs and
    the gdb front-end resolve to absolute store paths.
    """
    if require_toolchain:
        status = _toolchain.detect_probe_rs()
        if not status.present:
            # Lockfile-pinned probe-rs satisfies the requirement too.
            pinned = _resolve_probe_rs_via_lockfile(project_root)
            if pinned is None:
                raise ToolchainMissingError(
                    f"probe-rs is required for `alloy debug`.  Install: "
                    f"{status.install_hint}"
                )

    probe_rs_binary = (
        _resolve_probe_rs_via_lockfile(project_root) or "probe-rs"
    )

    server_args: list[str] = [
        probe_rs_binary,
        "gdb",
        "--chip",
        chip,
        "--gdb-connection-string",
        f"127.0.0.1:{gdb_port}",
        str(elf),
    ]
    if probe_kind != "auto":
        server_args.extend(["--probe", probe_kind])

    gdb_binary = _resolve_gdb(
        gdb_ui, require=require_toolchain, project_root=project_root
    )
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


__all__ = [
    "KNOWN_GDB_BINARIES",
    "DebugSession",
    "GdbNotFoundError",
    "build_invocation",
]
