"""Build orchestration — invokes ``cmake`` + ``ninja`` with toolchain detection.

The user-facing verb is ``alloy build``.  This module is the
business-logic layer; the Click wrapper is in
:mod:`alloy_cli.commands.build`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alloy_cli import __version__ as _alloy_cli_version
from alloy_cli.core import codegen as _codegen
from alloy_cli.core import lockfile_toolchain as _lockfile
from alloy_cli.core import process
from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core import toolchain_manager as _tm
from alloy_cli.core.codegen import RegenResult
from alloy_cli.core.errors import (
    AlloyCliError,
    FamilyToolchainInstallerVersionMismatchError,
    ToolchainMissingError,
)
from alloy_cli.core.events import record_event
from alloy_cli.core.memory import MemoryReport, parse_elf
from alloy_cli.core.project import PROJECT_FILE, AlloyDir, ProjectConfig, read

BuildProfile = Literal["debug", "release", "relwithdebinfo"]
SUPPORTED_PROFILES: tuple[BuildProfile, ...] = ("debug", "release", "relwithdebinfo")
PROFILE_TO_CMAKE = {
    "debug": "Debug",
    "release": "Release",
    "relwithdebinfo": "RelWithDebInfo",
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BuildResult:
    """What :func:`run` produced."""

    profile: BuildProfile
    build_dir: Path
    elf_path: Path | None
    memory: MemoryReport | None
    cmake_returncode: int
    build_returncode: int
    codegen_returncode: int | None = None
    codegen_skipped: bool = True
    codegen_reason: str = ""

    @property
    def ok(self) -> bool:
        if self.codegen_returncode is not None and self.codegen_returncode != 0:
            return False
        return self.cmake_returncode == 0 and self.build_returncode == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require(status_fn: Callable[[], object], *, name: str) -> None:
    """Raise :class:`ToolchainMissingError` when a status reports ``present=False``."""
    status = status_fn()
    if not getattr(status, "present", False):
        hint = getattr(status, "install_hint", None) or "install it from your distribution."
        raise ToolchainMissingError(
            f"{name} is required but not on PATH.  Install it: {hint}\n"
            "Run `alloy doctor` for full diagnostics."
        )


def _project_needs_cross_compile(config: ProjectConfig) -> bool:
    """A board with a Cortex-M / RISC-V / Xtensa core requires a cross-compiler."""
    if config.board is None and config.chip is None:
        return False
    # Heuristic: non-host targets are everything we ship.  We always
    # require arm-gcc until we model multi-arch toolchains in alloy-codegen.
    return True


def _resolve_elf(build_dir: Path, project_name: str) -> Path | None:
    """Find the produced firmware ELF inside ``build_dir``."""
    candidates: list[Path] = []
    direct = build_dir / f"{project_name}.elf"
    if direct.exists():
        candidates.append(direct)
    candidates.extend(sorted(build_dir.rglob(f"{project_name}.elf")))
    candidates.extend(sorted(build_dir.rglob("*.elf")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# CMake toolchain file generation (Wave 2)
# ---------------------------------------------------------------------------


# Map a pinned compiler tool name to the CMake variable assignments we
# emit when the lockfile pins it.  Adding a new compiler family is one
# entry here + ensuring the `binaries[]` of the family manifest declares
# every binary referenced.
_COMPILER_FAMILIES: dict[str, dict[str, str]] = {
    "arm-none-eabi-gcc": {
        "CMAKE_C_COMPILER": "arm-none-eabi-gcc",
        "CMAKE_CXX_COMPILER": "arm-none-eabi-g++",
        "CMAKE_ASM_COMPILER": "arm-none-eabi-gcc",
        "CMAKE_AR": "arm-none-eabi-ar",
        "CMAKE_RANLIB": "arm-none-eabi-ranlib",
        "CMAKE_OBJCOPY": "arm-none-eabi-objcopy",
        "CMAKE_OBJDUMP": "arm-none-eabi-objdump",
        "CMAKE_SIZE": "arm-none-eabi-size",
    },
    "xtensa-esp-elf-gcc": {
        "CMAKE_C_COMPILER": "xtensa-esp-elf-gcc",
        "CMAKE_CXX_COMPILER": "xtensa-esp-elf-g++",
        "CMAKE_ASM_COMPILER": "xtensa-esp-elf-gcc",
        "CMAKE_AR": "xtensa-esp-elf-ar",
        "CMAKE_RANLIB": "xtensa-esp-elf-ranlib",
        "CMAKE_OBJCOPY": "xtensa-esp-elf-objcopy",
        "CMAKE_OBJDUMP": "xtensa-esp-elf-objdump",
        "CMAKE_SIZE": "xtensa-esp-elf-size",
    },
    "riscv32-esp-elf-gcc": {
        "CMAKE_C_COMPILER": "riscv32-esp-elf-gcc",
        "CMAKE_CXX_COMPILER": "riscv32-esp-elf-g++",
        "CMAKE_ASM_COMPILER": "riscv32-esp-elf-gcc",
        "CMAKE_AR": "riscv32-esp-elf-ar",
        "CMAKE_RANLIB": "riscv32-esp-elf-ranlib",
        "CMAKE_OBJCOPY": "riscv32-esp-elf-objcopy",
        "CMAKE_OBJDUMP": "riscv32-esp-elf-objdump",
    },
    "riscv-none-elf-gcc": {
        "CMAKE_C_COMPILER": "riscv-none-elf-gcc",
        "CMAKE_CXX_COMPILER": "riscv-none-elf-g++",
        "CMAKE_ASM_COMPILER": "riscv-none-elf-gcc",
        "CMAKE_AR": "riscv-none-elf-ar",
        "CMAKE_RANLIB": "riscv-none-elf-ranlib",
        "CMAKE_OBJCOPY": "riscv-none-elf-objcopy",
        "CMAKE_OBJDUMP": "riscv-none-elf-objdump",
    },
}

_TOOLCHAIN_CMAKE_NAME = "toolchain.cmake"
_TOOLCHAIN_STAMP_NAME = "toolchain.cmake.stamp"


def _toolchain_stamp_payload(lockfile_text: str) -> str:
    """Stable JSON stamp = sha256(lockfile) + alloy-cli version."""
    sha = hashlib.sha256(lockfile_text.encode("utf-8")).hexdigest()[:16]
    return json.dumps(
        {"lockfile_sha": sha, "alloy_cli_version": _alloy_cli_version},
        sort_keys=True,
    )


def _resolve_pinned_path(
    tool_name: str,
    pin: _lockfile.ToolchainPin,
    binary_name: str,
) -> Path:
    """Return the absolute path inside the store for ``binary_name``.

    Raises :class:`FamilyToolchainInstallerVersionMismatchError` when
    the pinned ``(version, sha256)`` is not present in the local
    store — the user needs to run ``alloy toolchain install`` first.
    """
    installed = _tm.find_installed(tool_name, version=pin.version)
    if installed is None:
        raise FamilyToolchainInstallerVersionMismatchError(
            f"{tool_name} {pin.version} pinned in toolchain.lock but the "
            "store has no matching entry.  Run `alloy toolchain install`."
        )
    if installed.sha256 != pin.sha256:
        raise FamilyToolchainInstallerVersionMismatchError(
            f"{tool_name} {pin.version} sha256 in toolchain.lock differs "
            "from the store entry.  Run `alloy toolchain install --force` "
            "to repair the divergence."
        )
    candidate = installed.absolute_binary(binary_name)
    if candidate is None:
        # Bundled binary not declared in family manifest binaries[];
        # fall back to a conventional bin/ lookup.
        for sub in ("bin", "."):
            probe = installed.store_path / sub / binary_name
            if probe.exists():
                return probe
        raise FamilyToolchainInstallerVersionMismatchError(
            f"{tool_name} {pin.version}: cannot locate {binary_name} in "
            f"the store at {installed.store_path}.  The pin file may "
            "need to declare {binary_name} in binaries[]."
        )
    return candidate


def _render_toolchain_cmake(lock: _lockfile.ToolchainLock) -> str:
    """Build the toolchain.cmake content from a resolved lockfile.

    Walks every pinned tool whose name is a known compiler family
    (`_COMPILER_FAMILIES`) and emits the standard ``CMAKE_*`` variable
    assignments.  Tools the lockfile pins that aren't compiler families
    (e.g. probe-rs, cmake itself, ninja) are NOT projected into the
    toolchain file — flash / debug / build resolve those dynamically
    via ``toolchain_manager.resolve()``.
    """
    lines = [
        "# AUTO-GENERATED by alloy-cli — do not edit by hand.",
        "# Source: .alloy/toolchain.lock",
        "# Regenerate: edit toolchain.lock and re-run `alloy build`.",
        "",
    ]
    emitted_any = False
    for tool_name in sorted(lock.tools):
        pin = lock.tools[tool_name]
        mapping = _COMPILER_FAMILIES.get(tool_name)
        if mapping is None:
            continue
        emitted_any = True
        lines.append(f"# {tool_name} {pin.version}")
        for cmake_var, binary_name in mapping.items():
            path = _resolve_pinned_path(tool_name, pin, binary_name)
            lines.append(f'set({cmake_var} "{path}" CACHE FILEPATH "" FORCE)')
        lines.append("")
    if not emitted_any:
        # No compiler family pinned — keep CMake's default discovery.
        # Returning an empty file would be confusing; surface a comment
        # explaining the no-op.
        lines.append(
            "# No compiler family pinned in toolchain.lock; CMake will "
            "use its default discovery."
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def _generate_toolchain_cmake_if_stale(layout: AlloyDir) -> Path | None:
    """Generate ``.alloy/cache/toolchain.cmake`` under a stamp guard.

    Returns the path to the toolchain file when one was written (or
    is already current), or ``None`` when the project has no
    ``.alloy/toolchain.lock`` (legacy / Wave-1 projects keep building
    via PATH-resolved compilers).

    Stamp keying mirrors the codegen stamp pattern:
    ``sha256(lockfile_text) + alloy_cli_version``.  Either changing
    invalidates the stamp and forces regeneration.
    """
    lockfile_path = layout.base / _lockfile.LOCKFILE_NAME
    if not lockfile_path.exists():
        return None

    lockfile_text = lockfile_path.read_text(encoding="utf-8")
    expected_stamp = _toolchain_stamp_payload(lockfile_text)

    cache_dir = layout.cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    cmake_path = cache_dir / _TOOLCHAIN_CMAKE_NAME
    stamp_path = cache_dir / _TOOLCHAIN_STAMP_NAME

    if stamp_path.exists() and cmake_path.exists():
        try:
            actual_stamp = stamp_path.read_text(encoding="utf-8").strip()
        except OSError:
            actual_stamp = ""
        if actual_stamp == expected_stamp:
            return cmake_path

    # (Re)generate.  Reading the lockfile via the typed helper so we
    # surface ProjectConfigError on malformed content rather than a
    # raw tomllib decode error mid-build.
    lock = _lockfile.read(lockfile_path)
    content = _render_toolchain_cmake(lock)
    cmake_path.write_text(content, encoding="utf-8")
    stamp_path.write_text(expected_stamp, encoding="utf-8")
    return cmake_path


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run(
    *,
    project_root: Path,
    profile: BuildProfile = "debug",
    clean: bool = False,
    runner: process.CommandRunner | None = None,
    on_line: Callable[[str], None] | None = None,
    require_toolchain: bool = True,
    regen: bool = False,
    skip_codegen: bool = False,
    codegen_entry: _codegen.CodegenEntry | None = None,
) -> BuildResult:
    """Build ``project_root`` with the requested ``profile``.

    Returns a :class:`BuildResult`.  Raises :class:`ToolchainMissingError`
    when a required dependency is missing and ``require_toolchain`` is
    True (default).  Tests pass ``require_toolchain=False`` and a
    :class:`process.FakeRunner` to short-circuit the actual cmake call.

    ``regen`` forces a codegen pass; ``skip_codegen`` bypasses it
    entirely (useful for CI scenarios shipping pre-generated headers).
    Either flag wins over the stamp-cache logic.
    """
    if profile not in SUPPORTED_PROFILES:
        raise AlloyCliError(
            f"Unknown build profile {profile!r}.  Supported: {', '.join(SUPPORTED_PROFILES)}"
        )

    project_root = project_root.resolve()
    toml_path = project_root / PROJECT_FILE
    config = read(toml_path)

    if require_toolchain:
        _require(_toolchain.detect_cmake, name="cmake")
        _require(_toolchain.detect_ninja, name="ninja")
        if _project_needs_cross_compile(config):
            _require(_toolchain.detect_arm_gcc, name="arm-none-eabi-gcc")

    layout = AlloyDir(root=project_root)
    layout.ensure()
    record_event(layout, "build_started", profile=profile, clean=clean, regen=regen)
    build_dir = layout.base / "build"
    if clean and build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    # Codegen — runs before cmake so generated headers are in place.
    codegen_result: RegenResult | None = None
    if not skip_codegen:
        try:
            if regen:
                codegen_result = _codegen.force_regenerate(
                    config, layout, entry=codegen_entry, on_line=on_line
                )
            else:
                codegen_result = _codegen.regenerate_if_stale(
                    config, layout, entry=codegen_entry, on_line=on_line
                )
        except _codegen.CodegenError as exc:
            record_event(
                layout, "build_finished", profile=profile, returncode=-1, reason=str(exc)
            )
            return BuildResult(
                profile=profile,
                build_dir=build_dir,
                elf_path=None,
                memory=None,
                cmake_returncode=-1,
                build_returncode=-1,
                codegen_returncode=1,
                codegen_skipped=False,
                codegen_reason=str(exc),
            )
        if codegen_result.returncode is not None and codegen_result.returncode != 0:
            record_event(
                layout,
                "build_finished",
                profile=profile,
                returncode=codegen_result.returncode,
                reason=codegen_result.reason,
            )
            return BuildResult(
                profile=profile,
                build_dir=build_dir,
                elf_path=None,
                memory=None,
                cmake_returncode=-1,
                build_returncode=-1,
                codegen_returncode=codegen_result.returncode,
                codegen_skipped=codegen_result.skipped,
                codegen_reason=codegen_result.reason,
            )

    r = runner or process.runner

    # Toolchain file generation — only when a project lockfile exists.
    # Wave-2 contract: legacy projects without `.alloy/toolchain.lock`
    # keep building via CMake's PATH-resolved compilers, so the
    # invocation stays byte-identical with the pre-Wave-2 baseline.
    try:
        toolchain_cmake = _generate_toolchain_cmake_if_stale(layout)
    except FamilyToolchainInstallerVersionMismatchError as exc:
        record_event(
            layout,
            "build_finished",
            profile=profile,
            returncode=-1,
            stage="toolchain-resolve",
            reason=str(exc),
        )
        raise AlloyCliError(str(exc)) from exc

    # Configure
    configure_args = [
        "cmake",
        "-S",
        str(project_root),
        "-B",
        str(build_dir),
        "-G",
        "Ninja",
        f"-DCMAKE_BUILD_TYPE={PROFILE_TO_CMAKE[profile]}",
    ]
    if toolchain_cmake is not None:
        configure_args.append(
            f"-DCMAKE_TOOLCHAIN_FILE={toolchain_cmake}"
        )
    cfg = r.run(configure_args, on_line=on_line)
    if not cfg.ok:
        record_event(
            layout, "build_finished", profile=profile, returncode=cfg.returncode, stage="cmake"
        )
        return BuildResult(
            profile=profile,
            build_dir=build_dir,
            elf_path=None,
            memory=None,
            cmake_returncode=cfg.returncode,
            build_returncode=-1,
            codegen_returncode=codegen_result.returncode if codegen_result else None,
            codegen_skipped=codegen_result.skipped if codegen_result else True,
            codegen_reason=codegen_result.reason if codegen_result else "",
        )

    # Build
    build_args = ["cmake", "--build", str(build_dir)]
    bld = r.run(build_args, on_line=on_line)

    elf_path = _resolve_elf(build_dir, config.project.name) if bld.ok else None
    memory = parse_elf(elf_path, runner=r) if elf_path else None

    record_event(
        layout,
        "build_finished",
        profile=profile,
        returncode=bld.returncode,
        elf_path=str(elf_path) if elf_path else None,
        stage="ninja",
    )

    return BuildResult(
        profile=profile,
        build_dir=build_dir,
        elf_path=elf_path,
        memory=memory,
        cmake_returncode=cfg.returncode,
        build_returncode=bld.returncode,
        codegen_returncode=codegen_result.returncode if codegen_result else None,
        codegen_skipped=codegen_result.skipped if codegen_result else True,
        codegen_reason=codegen_result.reason if codegen_result else "",
    )


__all__ = [
    "PROFILE_TO_CMAKE",
    "SUPPORTED_PROFILES",
    "BuildProfile",
    "BuildResult",
    "run",
]
