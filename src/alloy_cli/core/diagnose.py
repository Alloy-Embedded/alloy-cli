"""Host-environment diagnostics — backs ``alloy doctor``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alloy_cli.core import toolchain as _toolchain
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
    except Exception as exc:
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


def run(*, project_dir: Path | None = None) -> DiagnosticReport:
    """Aggregate every diagnostic check into a single report."""
    project_dir = (project_dir or Path.cwd()).resolve()
    checks: list[CheckResult] = [
        _toolchain_check("cmake", _toolchain.detect_cmake),
        _toolchain_check("ninja", _toolchain.detect_ninja),
        _toolchain_check("arm-none-eabi-gcc", _toolchain.detect_arm_gcc),
        _toolchain_check("probe-rs", _toolchain.detect_probe_rs),
        _devices_submodule_check(),
        _project_check(project_dir),
    ]
    return DiagnosticReport(checks=tuple(checks))


__all__ = [
    "CheckResult",
    "CheckSeverity",
    "DiagnosticReport",
    "run",
]
