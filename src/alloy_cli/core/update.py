"""``alloy update`` orchestration — atomic upgrade of pinned components.

The user-facing flow is:

1. ``resolve_upgrades`` diffs the lockfile against the desired
   targets (alloy.toml or an explicit override).
2. ``apply_upgrades`` runs each component's :class:`ComponentUpgrader`
   in dependency order; the lockfile is rewritten only when **every**
   component reports success.

Every upgrader funnels its subprocess work through
:mod:`alloy_cli.core.process` so tests + the CLI share the same
seam.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from alloy_cli.core import process as _process
from alloy_cli.core.events import record_event
from alloy_cli.core.lockfile import AlloyLockfile, read_lock, write_lock
from alloy_cli.core.project import AlloyDir, ProjectConfig

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Upgrade:
    """One pending upgrade row."""

    component: str
    current: str | None
    target: str

    def is_change(self) -> bool:
        return self.current != self.target


@dataclass(frozen=True, slots=True)
class UpgradeOutcome:
    """Per-component result returned by a :class:`ComponentUpgrader`."""

    ok: bool
    log: str = ""
    restart_required: bool = False


@dataclass(frozen=True, slots=True)
class UpgradeContext:
    """Shared state passed to every upgrader."""

    project_dir: Path
    runner: _process.CommandRunner
    current_lock: AlloyLockfile


ComponentUpgrader = Callable[[Upgrade, UpgradeContext], UpgradeOutcome]


@dataclass(frozen=True, slots=True)
class UpgradeReport:
    """Aggregated outcome of :func:`apply_upgrades`."""

    new_lock: AlloyLockfile | None
    outcomes: tuple[tuple[Upgrade, UpgradeOutcome], ...] = field(default_factory=tuple)
    aborted: bool = False
    failure_component: str | None = None

    @property
    def restart_required(self) -> bool:
        return any(o.restart_required for _, o in self.outcomes)


# ---------------------------------------------------------------------------
# Built-in upgraders
# ---------------------------------------------------------------------------


def pip_upgrader(package_name: str, *, restart_required: bool = False) -> ComponentUpgrader:
    """Build a pip-driven upgrader for ``package_name``."""

    def _upgrader(upgrade: Upgrade, ctx: UpgradeContext) -> UpgradeOutcome:
        if not upgrade.is_change():
            return UpgradeOutcome(ok=True, log=f"{package_name}: already at {upgrade.target}")
        result = ctx.runner.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                f"{package_name}=={upgrade.target}",
            ],
            cwd=ctx.project_dir,
        )
        return UpgradeOutcome(
            ok=result.ok,
            log=(result.stdout + result.stderr).strip(),
            restart_required=restart_required and result.ok,
        )

    return _upgrader


def git_submodule_upgrader(upgrade: Upgrade, ctx: UpgradeContext) -> UpgradeOutcome:
    """Upgrade ``data/devices`` to the requested release tag.

    The repo's lockfile carries a version like ``1.5.0`` — we map that
    to a tag (`v1.5.0` first, then `1.5.0` as a fallback) and check it
    out inside the submodule.  Failure to find the tag is captured as a
    non-zero outcome.
    """
    if not upgrade.is_change():
        return UpgradeOutcome(ok=True, log=f"{upgrade.component}: already at {upgrade.target}")

    submodule = ctx.project_dir / "data" / "devices"
    if not submodule.exists():
        return UpgradeOutcome(
            ok=False,
            log=(
                f"{upgrade.component}: submodule {submodule} is not initialised.  "
                "Run `git submodule update --init`."
            ),
        )

    fetch = ctx.runner.run(["git", "fetch", "--tags", "origin"], cwd=submodule)
    if not fetch.ok:
        return UpgradeOutcome(
            ok=False,
            log=f"{upgrade.component}: git fetch failed.\n{fetch.stderr}".strip(),
        )

    for ref in (f"v{upgrade.target}", upgrade.target):
        checkout = ctx.runner.run(["git", "checkout", ref], cwd=submodule)
        if checkout.ok:
            return UpgradeOutcome(
                ok=True,
                log=f"{upgrade.component}: checked out {ref}",
            )
    return UpgradeOutcome(
        ok=False,
        log=(
            f"{upgrade.component}: neither v{upgrade.target} nor "
            f"{upgrade.target} resolved under {submodule}."
        ),
    )


# Component → upgrader.  Order matters: dependencies first.
UPGRADERS: dict[str, ComponentUpgrader] = {
    "alloy-devices-yml": git_submodule_upgrader,
    "alloy-codegen": pip_upgrader("alloy-codegen"),
    "alloy": pip_upgrader("alloy"),
    "alloy-cli": pip_upgrader("alloy-cli", restart_required=True),
}

DEPENDENCY_ORDER: tuple[str, ...] = (
    "alloy-devices-yml",
    "alloy-codegen",
    "alloy",
    "alloy-cli",
)


# ---------------------------------------------------------------------------
# Resolve / apply
# ---------------------------------------------------------------------------


def _component_target(config: ProjectConfig, component: str) -> str | None:
    aliases = {
        "alloy": config.project.alloy,
        "alloy-codegen": config.project.alloy_codegen,
        "alloy-devices-yml": config.project.alloy_devices_yml,
        "alloy-cli": config.project.alloy_cli,
    }
    return aliases.get(component)


def resolve_upgrades(
    config: ProjectConfig,
    lock: AlloyLockfile,
    *,
    available: dict[str, str] | None = None,
) -> tuple[Upgrade, ...]:
    """Compute the set of upgrades the user *would* apply.

    ``available`` overrides the alloy.toml-pinned target for each
    component — used by the CLI's `--check-remote` path or by tests
    that simulate "newer version is on PyPI".
    """
    available = available or {}
    out: list[Upgrade] = []
    for component, current in (
        ("alloy", lock.alloy),
        ("alloy-codegen", lock.alloy_codegen),
        ("alloy-devices-yml", lock.alloy_devices_yml),
        ("alloy-cli", lock.alloy_cli),
    ):
        target = available.get(component) or _component_target(config, component) or current
        if target is None:
            continue
        out.append(Upgrade(component=component, current=current, target=target))
    return tuple(out)


def _empty_lock() -> AlloyLockfile:
    return AlloyLockfile(
        schema_version="1.0.0",
        alloy=None,
        alloy_codegen=None,
        alloy_devices_yml=None,
        alloy_cli=None,
    )


def _ordered_upgrades(upgrades: Iterable[Upgrade]) -> tuple[Upgrade, ...]:
    """Filter to only the components that actually need to change, ordered."""
    by_name = {u.component: u for u in upgrades if u.is_change()}
    return tuple(by_name[name] for name in DEPENDENCY_ORDER if name in by_name)


def _build_new_lock(upgrades: Iterable[Upgrade], previous: AlloyLockfile) -> AlloyLockfile:
    by_component = {u.component: u for u in upgrades}

    def _value(component: str, fallback: str | None) -> str | None:
        upgrade = by_component.get(component)
        return upgrade.target if upgrade is not None else fallback

    return AlloyLockfile(
        schema_version="1.0.0",
        alloy=_value("alloy", previous.alloy),
        alloy_codegen=_value("alloy-codegen", previous.alloy_codegen),
        alloy_devices_yml=_value("alloy-devices-yml", previous.alloy_devices_yml),
        alloy_cli=_value("alloy-cli", previous.alloy_cli),
    )


def apply_upgrades(
    project_root: Path,
    *,
    upgrades: tuple[Upgrade, ...],
    config: ProjectConfig,
    dry_run: bool = False,
    runner: _process.CommandRunner | None = None,
    upgraders: dict[str, ComponentUpgrader] | None = None,
) -> UpgradeReport:
    """Run each upgrader in dependency order; rewrite the lockfile on success.

    ``dry_run`` skips both the upgraders **and** the lockfile rewrite,
    leaving every component untouched (the CLI prints the proposed
    upgrades and exits).  When at least one upgrader returns
    ``ok=False`` the lockfile is **not** rewritten and the report
    surfaces the failing component name.
    """
    layout = AlloyDir(root=project_root)
    layout.ensure()
    previous_lock = read_lock(layout.lockfile) if layout.lockfile.exists() else _empty_lock()

    ordered = _ordered_upgrades(upgrades)
    if not ordered:
        return UpgradeReport(new_lock=previous_lock, outcomes=(), aborted=False)

    if dry_run:
        return UpgradeReport(
            new_lock=previous_lock,
            outcomes=tuple(
                (u, UpgradeOutcome(ok=True, log="dry-run", restart_required=False)) for u in ordered
            ),
            aborted=False,
        )

    upgraders = upgraders or UPGRADERS
    ctx = UpgradeContext(
        project_dir=project_root,
        runner=runner or _process.runner,
        current_lock=previous_lock,
    )
    outcomes: list[tuple[Upgrade, UpgradeOutcome]] = []
    for upgrade in ordered:
        upgrader = upgraders.get(upgrade.component)
        if upgrader is None:
            outcome = UpgradeOutcome(
                ok=False, log=f"no upgrader registered for {upgrade.component}"
            )
        else:
            outcome = upgrader(upgrade, ctx)
        outcomes.append((upgrade, outcome))
        if outcome.ok:
            record_event(
                layout,
                "update_completed",
                component=upgrade.component,
                target=upgrade.target,
                restart_required=outcome.restart_required,
            )
        if not outcome.ok:
            return UpgradeReport(
                new_lock=None,
                outcomes=tuple(outcomes),
                aborted=True,
                failure_component=upgrade.component,
            )

    new_lock = _build_new_lock(ordered, previous_lock)
    write_lock(layout.lockfile, new_lock)
    return UpgradeReport(new_lock=new_lock, outcomes=tuple(outcomes), aborted=False)


__all__ = [
    "DEPENDENCY_ORDER",
    "UPGRADERS",
    "ComponentUpgrader",
    "Upgrade",
    "UpgradeContext",
    "UpgradeOutcome",
    "UpgradeReport",
    "apply_upgrades",
    "git_submodule_upgrader",
    "pip_upgrader",
    "resolve_upgrades",
]
