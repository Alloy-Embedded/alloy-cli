"""``alloy update`` orchestration — atomic upgrade of pinned components."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alloy_cli.core.lockfile import AlloyLockfile, read_lock, write_lock
from alloy_cli.core.project import AlloyDir, ProjectConfig


@dataclass(frozen=True, slots=True)
class Upgrade:
    """One pending upgrade row."""

    component: str
    current: str | None
    target: str

    def is_change(self) -> bool:
        return self.current != self.target


def _component_target(config: ProjectConfig, component: str) -> str | None:
    """Pull the target version from ``alloy.toml [project]`` if pinned."""
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


def apply_upgrades(
    project_root: Path,
    *,
    upgrades: tuple[Upgrade, ...],
    config: ProjectConfig,
    dry_run: bool = False,
) -> AlloyLockfile:
    """Write a refreshed ``.alloy/version.lock`` once every upgrade lands.

    Today this is purely a lockfile rewrite — actual pip / git
    upgrades land with the per-component upgraders.  The atomic
    contract is preserved by writing the new lock only after every
    component reports success (today every component is a no-op).
    """
    layout = AlloyDir(root=project_root)
    layout.ensure()
    if not upgrades:
        return (
            read_lock(layout.lockfile)
            if layout.lockfile.exists()
            else AlloyLockfile(
                schema_version="1.0.0",
                alloy=None,
                alloy_codegen=None,
                alloy_devices_yml=None,
                alloy_cli=None,
            )
        )
    by_component = {u.component: u for u in upgrades}
    new_lock = AlloyLockfile(
        schema_version="1.0.0",
        alloy=by_component.get("alloy", _stub("alloy")).target,
        alloy_codegen=by_component.get("alloy-codegen", _stub("alloy-codegen")).target,
        alloy_devices_yml=by_component.get("alloy-devices-yml", _stub("alloy-devices-yml")).target,
        alloy_cli=by_component.get("alloy-cli", _stub("alloy-cli")).target,
    )
    if not dry_run:
        write_lock(layout.lockfile, new_lock)
    return new_lock


def _stub(name: str) -> Upgrade:
    return Upgrade(component=name, current=None, target=None)  # type: ignore[arg-type]


__all__ = ["Upgrade", "apply_upgrades", "resolve_upgrades"]
