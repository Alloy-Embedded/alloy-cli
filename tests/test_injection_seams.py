"""Static guards for the injection-seam contract (#23).

`core.X` modules MUST expose stub-able functions through
``from alloy_cli.core import X as _X`` rather than direct
``from alloy_cli.core.X import detect_*`` imports.  Otherwise
tests have to monkey-patch every importer's local copy of the
binding to stub a single function.

This module walks the source tree and asserts:

1. No module under ``src/alloy_cli/`` imports a ``detect_*``
   name directly from ``alloy_cli.core.toolchain``.
2. ``core.peripherals`` does not re-introduce the local
   ``_emit_toml`` helper after the dedup'd
   :func:`core.project.dumps` landed.
3. ``core.project.dumps`` is idempotent on a round-trip
   through :func:`core.project.read`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from alloy_cli.core.project import (
    PROJECT_FILE,
    BoardRef,
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
    dumps,
    read,
    write,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src" / "alloy_cli"


def _iter_python_modules(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _direct_detect_imports(path: Path) -> list[str]:
    """Return the names imported via `from alloy_cli.core.toolchain import …`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "alloy_cli.core.toolchain":
            for alias in node.names:
                if alias.name.startswith("detect_"):
                    offenders.append(alias.name)
    return offenders


def test_no_direct_detect_imports_under_src() -> None:
    """No module imports a `detect_*` name directly from core.toolchain."""
    bad: dict[Path, list[str]] = {}
    for path in _iter_python_modules(_SRC):
        offenders = _direct_detect_imports(path)
        if offenders:
            bad[path.relative_to(_REPO_ROOT)] = offenders
    assert not bad, (
        "Direct `from alloy_cli.core.toolchain import detect_*` imports survive — "
        "switch to `from alloy_cli.core import toolchain as _toolchain` so tests "
        "can stub `_toolchain.detect_*` once.\n"
        + "\n".join(f"  {path}: {names}" for path, names in bad.items())
    )


def test_peripherals_does_not_define_local_emit_toml() -> None:
    """The single TOML emitter contract: only core.project.dumps."""
    body = (_SRC / "core" / "peripherals.py").read_text(encoding="utf-8")
    assert "_emit_toml" not in body, (
        "core.peripherals re-introduced _emit_toml — replace with "
        "`from alloy_cli.core.project import dumps`."
    )


def test_dumps_round_trip_is_byte_stable(tmp_path) -> None:
    """A dumps → read → dumps round-trip is byte-identical."""
    config = ProjectConfig(
        schema_version="1.1.0",
        project=ProjectMeta(name="firmware", alloy_cli="0.5.0"),
        board=BoardRef(id="nucleo_g071rb"),
        chip=None,
        clocks={"profile": "default_pll_64mhz"},
        peripherals=(
            PeripheralEntry(
                kind="uart",
                name="console",
                payload={
                    "kind": "uart",
                    "name": "console",
                    "peripheral": "USART2",
                    "tx": "PA2",
                    "rx": "PA3",
                    "baud": 115200,
                },
            ),
        ),
        build={"profile": "release"},
        flash={},
        raw={},
    )

    first = dumps(config)
    target = tmp_path / PROJECT_FILE
    write(target, config)
    assert target.read_text(encoding="utf-8") == first

    parsed = read(target)
    second = dumps(parsed)
    assert second == first


def test_dumps_round_trip_preserves_chip_target(tmp_path) -> None:
    config = ProjectConfig(
        schema_version="1.1.0",
        project=ProjectMeta(name="firmware"),
        board=None,
        chip=ChipRef(vendor="st", family="stm32g0", device="stm32g071rb"),
        clocks={},
        peripherals=(),
        build={},
        flash={},
        raw={},
    )
    target = tmp_path / PROJECT_FILE
    write(target, config)

    reloaded = read(target)
    assert dumps(reloaded) == dumps(config)


@pytest.mark.parametrize(
    "screen_module,offending_locals",
    [
        ("alloy_cli.tui.screens.dashboard", ("detect_arm_gcc", "detect_cmake", "detect_probe_rs")),
    ],
)
def test_dashboard_uses_module_relative_toolchain_lookups(
    screen_module: str, offending_locals: tuple[str, ...]
) -> None:
    """The dashboard module should NOT carry module-local detect_* names.

    If it does, tests would have to rebind them every time —
    re-introducing the bug the seam refactor aimed to kill.
    """
    import importlib

    module = importlib.import_module(screen_module)
    for name in offending_locals:
        assert not hasattr(module, name), (
            f"{screen_module}.{name} resurfaced — keep the lookup behind "
            "`_toolchain.detect_*` so a single stub propagates."
        )
