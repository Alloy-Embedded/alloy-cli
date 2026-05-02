"""Host-environment diagnostics — backs ``alloy doctor``.

Beyond the read-only check surface, this module also ships an
:data:`AUTO_FIXERS` registry that the TUI ``DoctorScreen`` and the
``alloy doctor --fix`` CLI both consume.  Auto-fixers run via
:class:`alloy_cli_core_process_CommandRunner` so tests share the
same subprocess seam as the rest of the codebase.

Wave-1 of the toolchain-management track makes :func:`run`
*family-aware*: when an MCU family resolves (from ``alloy.toml`` or
the explicit ``family=...`` argument), the toolchain check list
comes from ``data/families/<family_id>.yml`` instead of the legacy
hard-coded set.  Projects without a resolvable family see the
exact same generic checks the pre-Wave-1 doctor produced.
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core import toolchain_registry as _registry
from alloy_cli.core.errors import BoardNotFoundError, FamilyToolchainError, ProjectConfigError
from alloy_cli.core.process import CommandRunner
from alloy_cli.core.process import runner as _default_runner
from alloy_cli.core.project import PROJECT_FILE, ProjectConfig, read

CheckSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One row in the diagnostic report.

    ``source`` answers "where would this tool come from?" for
    toolchain rows: ``"system"`` (already on PATH), ``"xpack"``,
    ``"github:<owner>/<repo>"``, ``"probe-rs-installer"``,
    ``"espressif"``, or ``"vendor (EULA — install manually)"``.
    Non-toolchain rows leave it ``None``.
    """

    name: str
    ok: bool
    severity: CheckSeverity
    message: str
    install_hint: str | None = None
    auto_fix: str | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """Aggregated output of :func:`run`."""

    checks: tuple[CheckResult, ...]

    @property
    def has_errors(self) -> bool:
        return any(c.severity == "error" and not c.ok for c in self.checks)

    def to_dict(self) -> dict[str, object]:
        # ``schema_version`` bumped to 1.1 in Wave-1: every check
        # entry now carries a `source` key (`null` for non-toolchain
        # rows).  Older clients reading 1.0 keep working — every
        # 1.0 field is preserved verbatim.
        return {
            "schema_version": "1.1",
            "ok": not self.has_errors,
            "checks": [
                {
                    "name": c.name,
                    "ok": c.ok,
                    "severity": c.severity,
                    "message": c.message,
                    "install_hint": c.install_hint,
                    "auto_fix": c.auto_fix,
                    "source": c.source,
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Detector dispatcher (family-aware path)
# ---------------------------------------------------------------------------


_VENDOR_SOURCE_LABEL = "vendor (EULA — install manually)"


# Tool name → name of the typed detector in ``core.toolchain``.
# Stored as a string (not a function reference) so monkeypatching
# ``_toolchain.detect_*`` in tests is picked up at call time
# instead of being frozen at import.  Adding a detector here is
# opt-in: only binaries whose name on PATH matches the manifest's
# ``tool`` field get richer output (version string, OS-specific
# install hint).  Everything else flows through
# :func:`_check_generic_tool` which falls back to ``shutil.which``.
_DEDICATED_DETECTORS: dict[str, str] = {
    "arm-none-eabi-gcc": "detect_arm_gcc",
    "cmake": "detect_cmake",
    "ninja": "detect_ninja",
    "probe-rs": "detect_probe_rs",
    "openocd": "detect_openocd",
}


def _resolve_dedicated_detector(
    tool_name: str,
) -> Callable[[], _toolchain.ToolchainStatus] | None:
    """Late-bind the detector so test monkeypatches on
    ``_toolchain.detect_*`` are honoured.
    """
    attr = _DEDICATED_DETECTORS.get(tool_name)
    if attr is None:
        return None
    fn = getattr(_toolchain, attr, None)
    if not callable(fn):
        return None
    return cast(Callable[[], _toolchain.ToolchainStatus], fn)


_OS_DOC_KEYS: dict[str, str] = {
    "darwin": "macos",
    "linux": "linux",
    "windows": "windows",
}


def _per_os_install_doc(tool_req: _registry.ToolRequirement) -> str | None:
    """Pick the install doc URL for the active OS, falling back to any URL."""
    if not tool_req.install_docs:
        return None
    os_key = _OS_DOC_KEYS.get(platform.system().lower())
    if os_key and os_key in tool_req.install_docs:
        return tool_req.install_docs[os_key]
    # Fallback: return any URL so the user has *something* clickable.
    return next(iter(tool_req.install_docs.values()), None)


def _from_dedicated_detector(
    tool_req: _registry.ToolRequirement,
    status: _toolchain.ToolchainStatus,
) -> CheckResult:
    """Project a typed :class:`ToolchainStatus` to a :class:`CheckResult`."""
    if status.present:
        version = f" {status.version}" if status.version else ""
        return CheckResult(
            name=tool_req.tool,
            ok=True,
            severity="info",
            message=f"{tool_req.tool}{version} at {status.path}",
            source="system",
        )
    return CheckResult(
        name=tool_req.tool,
        ok=False,
        severity="error",
        message=f"{tool_req.tool} is not on PATH.",
        install_hint=status.install_hint,
        source=tool_req.source,
    )


def _check_generic_tool(tool_req: _registry.ToolRequirement) -> CheckResult:
    """Detect a tool that has no dedicated ``core.toolchain`` helper.

    Vendor-source missing tools surface as ``severity="info"`` with the
    OS-appropriate install doc URL — never as errors, since we cannot
    redistribute EULA-gated binaries.
    """
    path = shutil.which(tool_req.tool)
    if path is not None:
        return CheckResult(
            name=tool_req.tool,
            ok=True,
            severity="info",
            message=f"{tool_req.tool} at {path}",
            source="system",
        )
    if tool_req.is_vendor:
        doc_url = _per_os_install_doc(tool_req)
        return CheckResult(
            name=tool_req.tool,
            ok=False,
            severity="info",
            message=f"{tool_req.tool} not on PATH (EULA-gated; install manually).",
            install_hint=doc_url,
            source=_VENDOR_SOURCE_LABEL,
        )
    # Non-vendor missing tool: red row, but Wave-1 has no installer.
    return CheckResult(
        name=tool_req.tool,
        ok=False,
        severity="error",
        message=f"{tool_req.tool} not on PATH.",
        install_hint=f"Wave-2 will install via {tool_req.source}.",
        source=tool_req.source,
    )


def _check_for_tool(tool_req: _registry.ToolRequirement) -> CheckResult:
    detector = _resolve_dedicated_detector(tool_req.tool)
    if detector is not None:
        return _from_dedicated_detector(tool_req, detector())
    return _check_generic_tool(tool_req)


def _checks_from_manifest(manifest: _registry.FamilyManifest) -> list[CheckResult]:
    """Run every required + recommended + optional tool through the dispatcher.

    Order is preserved so the doctor table reads "required first,
    then recommended, then optional" — easy to scan.
    """
    out: list[CheckResult] = []
    for tier in (manifest.required, manifest.recommended, manifest.optional):
        for tool_req in tier:
            out.append(_check_for_tool(tool_req))
    return out


# ---------------------------------------------------------------------------
# Legacy generic toolchain checks (no family resolved)
# ---------------------------------------------------------------------------


def _toolchain_check(name: str, status_fn: Callable[[], _toolchain.ToolchainStatus]) -> CheckResult:
    """Pre-Wave-1 detector wrapper, used when no family resolves.

    Output stays byte-identical to the legacy doctor except for the
    new ``source`` field (always ``None`` — the legacy path doesn't
    know the manifest's source vocabulary).
    """
    status = status_fn()
    if status.present:
        return CheckResult(
            name=name,
            ok=True,
            severity="info",
            message=f"{name} {status.version or ''} at {status.path}".strip(),
        )
    return CheckResult(
        name=name,
        ok=False,
        severity="error",
        message=f"{name} is not on PATH.",
        install_hint=status.install_hint,
    )


def _legacy_toolchain_checks() -> list[CheckResult]:
    return [
        _toolchain_check("cmake", _toolchain.detect_cmake),
        _toolchain_check("ninja", _toolchain.detect_ninja),
        _toolchain_check("arm-none-eabi-gcc", _toolchain.detect_arm_gcc),
        _toolchain_check("probe-rs", _toolchain.detect_probe_rs),
    ]


# ---------------------------------------------------------------------------
# Project / submodule / extras / accessibility checks
# ---------------------------------------------------------------------------


def _project_check(project_dir: Path) -> CheckResult:
    toml = project_dir / PROJECT_FILE
    if not toml.exists():
        return CheckResult(
            name="alloy.toml",
            ok=False,
            severity="warning",
            message=f"No alloy.toml at {project_dir}.",
            install_hint="Run `alloy new` to scaffold a project.",
        )
    try:
        config = read(toml)
    except (ProjectConfigError, OSError) as exc:
        return CheckResult(
            name="alloy.toml",
            ok=False,
            severity="error",
            message=f"alloy.toml failed to parse: {exc}",
        )
    return CheckResult(
        name="alloy.toml",
        ok=True,
        severity="info",
        message=f"project={config.project.name} schema={config.schema_version}",
    )


def _devices_submodule_check() -> CheckResult:
    from alloy_cli.core.ir import data_devices_root

    root = data_devices_root()
    vendors = root / "vendors"
    if not vendors.exists():
        return CheckResult(
            name="alloy-devices-yml",
            ok=False,
            severity="warning",
            message="alloy-devices-yml submodule is not initialised.",
            install_hint="git submodule update --init",
            auto_fix="git submodule update --init",
        )
    return CheckResult(
        name="alloy-devices-yml",
        ok=True,
        severity="info",
        message=f"vendors directory present at {vendors}",
    )


def _mcp_extras_check() -> CheckResult:
    """The `mcp` Python optional dep — required for the official SDK transport."""
    if importlib.util.find_spec("mcp") is not None:
        return CheckResult(
            name="mcp",
            ok=True,
            severity="info",
            message="MCP SDK installed (pip install alloy-cli[mcp]).",
        )
    return CheckResult(
        name="mcp",
        ok=False,
        severity="warning",
        message="MCP optional dependency missing; the stdio fallback transport is in use.",
        install_hint="pip install 'alloy-cli[mcp]'",
        auto_fix="pip install 'alloy-cli[mcp]'",
    )


def _accessibility_check() -> CheckResult:
    """Surface the active terminal's accessibility-relevant env vars.

    No auto-fix — we just give the user a single place to confirm
    that NO_COLOR / TERM / COLORTERM are set the way they expect.
    """
    import os

    no_color = os.environ.get("NO_COLOR", "")
    term = os.environ.get("TERM", "")
    colorterm = os.environ.get("COLORTERM", "")
    parts: list[str] = []
    if no_color:
        parts.append(f"NO_COLOR={no_color}")
    if term:
        parts.append(f"TERM={term}")
    if colorterm:
        parts.append(f"COLORTERM={colorterm}")
    summary = ", ".join(parts) or "(default terminal)"
    return CheckResult(
        name="accessibility-suite",
        ok=True,
        severity="info",
        message=f"terminal: {summary}",
    )


# ---------------------------------------------------------------------------
# Family resolution
# ---------------------------------------------------------------------------


def _resolve_family_for_run(
    project_dir: Path, family_override: str | None
) -> tuple[_registry.FamilyManifest | None, CheckResult | None]:
    """Pick the manifest the toolchain section will be built from.

    Returns ``(manifest, note)`` where ``note`` is an info/error
    :class:`CheckResult` rendered alongside the toolchain rows when
    family resolution failed in a way the user should hear about
    (explicit override pointed at an unknown family; project's
    chip/board resolved to a family with no shipped manifest).
    """
    if family_override is not None:
        try:
            return _registry.load_family(family_override), None
        except FamilyToolchainError as exc:
            return None, CheckResult(
                name="toolchain-family",
                ok=False,
                severity="error",
                message=f"--for {family_override!r}: {exc}",
                install_hint=(
                    f"Known families: {', '.join(_registry.known_families())}"
                ),
                source=None,
            )

    toml = project_dir / PROJECT_FILE
    if not toml.exists():
        return None, None
    try:
        config = read(toml)
    except (ProjectConfigError, OSError):
        return None, None

    family_id = _project_family_id(config)
    if family_id is None:
        return None, None

    try:
        return _registry.load_family(family_id), None
    except FamilyToolchainError:
        return None, CheckResult(
            name="toolchain-family",
            ok=True,
            severity="info",
            message=(
                f"No toolchain manifest for family {family_id!r}; "
                "falling back to generic checks."
            ),
            install_hint=(
                "Add a manifest under data/families/ — see "
                "docs/TOOLCHAIN_REGISTRY.md."
            ),
            source=None,
        )


def _project_family_id(config: ProjectConfig) -> str | None:
    """Mirror the precedence in ``toolchain_registry.resolve_for_project``."""
    if config.chip is not None:
        return config.chip.family or None
    if config.board is not None:
        from alloy_cli.core import boards as _boards

        try:
            return _boards.lookup(config.board.id).family or None
        except BoardNotFoundError:
            return None
    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    *,
    project_dir: Path | None = None,
    family: str | None = None,
) -> DiagnosticReport:
    """Aggregate every diagnostic check into a single report.

    ``family`` overrides the project's resolved family (useful before
    scaffolding when no ``alloy.toml`` exists yet).  When neither
    ``family`` nor a project-derived family resolves, the legacy
    generic check list runs — output shape stays byte-compatible
    with the pre-Wave-1 doctor except for the new ``source`` field
    (``None`` everywhere on the legacy path).
    """
    project_dir = (project_dir or Path.cwd()).resolve()

    manifest, family_note = _resolve_family_for_run(project_dir, family)

    if manifest is not None:
        toolchain_checks = _checks_from_manifest(manifest)
    else:
        toolchain_checks = _legacy_toolchain_checks()

    other_checks: list[CheckResult] = [
        _devices_submodule_check(),
        _mcp_extras_check(),
        _project_check(project_dir),
        _accessibility_check(),
    ]

    all_checks: list[CheckResult] = list(toolchain_checks)
    if family_note is not None:
        all_checks.append(family_note)
    all_checks.extend(other_checks)

    return DiagnosticReport(checks=tuple(all_checks))


# ---------------------------------------------------------------------------
# Auto-fix registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AutoFixOutcome:
    """Result of applying an auto-fix.

    ``ok`` mirrors the underlying subprocess return code; ``log`` is
    the captured stdout/stderr the screen renders verbatim.
    """

    ok: bool
    log: str = ""


AutoFix = Callable[[CheckResult, CommandRunner, Path], AutoFixOutcome]
"""Typed callable for an auto-fixer.

Receives the failing :class:`CheckResult`, a :class:`CommandRunner`
seam (so tests can supply a :class:`FakeRunner`), and the project
root.  Returns an :class:`AutoFixOutcome`.
"""


def _auto_fix_init_devices_submodule(
    check: CheckResult, runner: CommandRunner, project_root: Path
) -> AutoFixOutcome:
    """Idempotent ``git submodule update --init`` from the project root."""
    del check  # unused — fixer is keyed by check name
    result = runner.run(
        ["git", "submodule", "update", "--init"], cwd=project_root
    )
    log = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return AutoFixOutcome(ok=result.ok, log=log)


def _auto_fix_pip_install_mcp(
    check: CheckResult, runner: CommandRunner, project_root: Path
) -> AutoFixOutcome:
    """``pip install alloy-cli[mcp]`` — adds the optional MCP SDK."""
    del check, project_root  # unused — keyed by check name; pip is global
    result = runner.run(["pip", "install", "alloy-cli[mcp]"])
    log = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return AutoFixOutcome(ok=result.ok, log=log)


# Mapping CheckResult.name → AutoFix.  Adding a check with an
# ``auto_fix`` string is necessary but not sufficient — the entry
# must also appear here.  Tests pin the contents of this dict so
# regressions surface immediately.
AUTO_FIXERS: dict[str, AutoFix] = {
    "alloy-devices-yml": _auto_fix_init_devices_submodule,
    "mcp": _auto_fix_pip_install_mcp,
}


def get_auto_fix(check: CheckResult) -> AutoFix | None:
    """Return the registered fixer for ``check`` or ``None``.

    A fixer is available iff the check carries a non-None
    ``auto_fix`` AND the registry has an entry under
    :attr:`CheckResult.name`.  Both conditions matter so checks
    that *describe* a manual fix (with ``auto_fix=None``) keep
    ``f`` disabled in the TUI.
    """
    if check.auto_fix is None:
        return None
    return AUTO_FIXERS.get(check.name)


def apply_auto_fix(
    check: CheckResult,
    *,
    project_root: Path,
    runner: CommandRunner | None = None,
) -> AutoFixOutcome:
    """Run the registered auto-fix for ``check``.

    Raises :class:`KeyError` when the check has no fixer — callers
    should pre-check via :func:`get_auto_fix` and fall back to a
    user-facing notification when one isn't available.
    """
    fixer = get_auto_fix(check)
    if fixer is None:
        raise KeyError(f"No auto-fix registered for {check.name!r}")
    return fixer(check, runner or _default_runner, project_root)


__all__ = [
    "AUTO_FIXERS",
    "AutoFix",
    "AutoFixOutcome",
    "CheckResult",
    "CheckSeverity",
    "DiagnosticReport",
    "apply_auto_fix",
    "get_auto_fix",
    "run",
]
