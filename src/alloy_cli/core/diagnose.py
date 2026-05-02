"""Host-environment diagnostics — backs ``alloy doctor``.

Beyond the read-only check surface, this module also ships an
:data:`AUTO_FIXERS` registry that the TUI ``DoctorScreen`` and the
``alloy doctor --fix`` CLI both consume.  Auto-fixers run via
:class:`alloy_cli.core.process.CommandRunner` so tests share the
same subprocess seam as the rest of the codebase.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alloy_cli.core import toolchain as _toolchain
from alloy_cli.core.errors import ProjectConfigError
from alloy_cli.core.process import CommandRunner
from alloy_cli.core.process import runner as _default_runner
from alloy_cli.core.project import PROJECT_FILE, read

CheckSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One row in the diagnostic report."""

    name: str
    ok: bool
    severity: CheckSeverity
    message: str
    install_hint: str | None = None
    auto_fix: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """Aggregated output of :func:`run`."""

    checks: tuple[CheckResult, ...]

    @property
    def has_errors(self) -> bool:
        return any(c.severity == "error" and not c.ok for c in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "ok": not self.has_errors,
            "checks": [
                {
                    "name": c.name,
                    "ok": c.ok,
                    "severity": c.severity,
                    "message": c.message,
                    "install_hint": c.install_hint,
                    "auto_fix": c.auto_fix,
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _toolchain_check(name: str, status_fn: Callable[[], _toolchain.ToolchainStatus]) -> CheckResult:
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


def run(*, project_dir: Path | None = None) -> DiagnosticReport:
    """Aggregate every diagnostic check into a single report."""
    project_dir = (project_dir or Path.cwd()).resolve()
    checks: list[CheckResult] = [
        _toolchain_check("cmake", _toolchain.detect_cmake),
        _toolchain_check("ninja", _toolchain.detect_ninja),
        _toolchain_check("arm-none-eabi-gcc", _toolchain.detect_arm_gcc),
        _toolchain_check("probe-rs", _toolchain.detect_probe_rs),
        _devices_submodule_check(),
        _mcp_extras_check(),
        _project_check(project_dir),
        _accessibility_check(),
    ]
    return DiagnosticReport(checks=tuple(checks))


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
