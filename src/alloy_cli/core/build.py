"""Build orchestration — invokes ``cmake`` + ``ninja`` with toolchain detection.

The user-facing verb is ``alloy build``.  This module is the
business-logic layer; the Click wrapper is in
:mod:`alloy_cli.commands.build`.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alloy_cli.core import codegen as _codegen
from alloy_cli.core import process
from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core.codegen import RegenResult
from alloy_cli.core.errors import AlloyCliError, ToolchainMissingError
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
