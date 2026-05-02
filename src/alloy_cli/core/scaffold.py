"""Project scaffolder used by ``alloy new``.

Pure function ``scaffold(...)`` writes a complete project tree from a
``ScaffoldRequest`` and returns a ``ScaffoldResult``.  Knows nothing
about Click or terminal output — that lives in ``commands.new``.

The scaffolder picks board-driven defaults when the user passes
``--board`` (debug-UART peripheral, LED GPIO, clock profile) and
falls back to a chip-only project when ``--device`` is used.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from alloy_cli import __version__ as _alloy_cli_version
from alloy_cli.core import boards as _boards
from alloy_cli.core import ir as _ir
from alloy_cli.core.errors import AlloyCliError, BoardNotFoundError, DeviceNotFoundError
from alloy_cli.core.project import (
    PROJECT_FILE,
    SCHEMA_VERSION,
    BoardRef,
    ChipRef,
    PeripheralEntry,
    ProjectConfig,
    ProjectMeta,
    write,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


PROJECT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
SUPPORTED_LICENSES = ("MIT", "Apache-2.0", "BSD-3")
ALLOY_CLI_HOMEPAGE = "https://github.com/Alloy-Embedded/alloy-cli"


class ScaffoldError(AlloyCliError):
    """User-facing scaffold failures (bad name, non-empty dest, …)."""

    error_type = "scaffold-error"


# ---------------------------------------------------------------------------
# Request / result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScaffoldRequest:
    """Inputs for :func:`scaffold`.

    Exactly one of ``board_id`` / ``device`` must be supplied.  The
    ``device`` form is a 3-tuple ``(vendor, family, device)``.
    """

    name: str
    destination: Path
    board_id: str | None = None
    device: tuple[str, str, str] | None = None
    license: str = "MIT"
    author: str = "Alloy User"
    init_git: bool = True
    force: bool = False


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    """What :func:`scaffold` wrote."""

    name: str
    destination: Path
    files_written: tuple[Path, ...]
    target_label: str
    config: ProjectConfig = field(repr=False)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_project_name(name: str) -> None:
    if not PROJECT_NAME_RE.match(name):
        raise ScaffoldError(
            f"Project name {name!r} is not valid.  "
            f"Must match {PROJECT_NAME_RE.pattern} (letter, then letters/digits/_/-)."
        )


def _validate_destination(dest: Path, *, force: bool) -> None:
    if dest.exists() and any(dest.iterdir()) and not force:
        existing = sorted(p.name for p in dest.iterdir())[:5]
        raise ScaffoldError(
            f"Destination {dest} is not empty (e.g. {', '.join(existing)}).  "
            f"Pass --force to overwrite, or pick a fresh path."
        )


def _validate_license(license_id: str) -> None:
    if license_id not in SUPPORTED_LICENSES:
        raise ScaffoldError(
            f"Unsupported license {license_id!r}.  Pick one of: {', '.join(SUPPORTED_LICENSES)}."
        )


def _validate_request(req: ScaffoldRequest) -> None:
    validate_project_name(req.name)
    _validate_license(req.license)
    if (req.board_id is None) == (req.device is None):
        raise ScaffoldError(
            "Specify exactly one of --board or --device.  "
            "Run `alloy boards` or `alloy devices` to discover options."
        )


# ---------------------------------------------------------------------------
# Board/chip resolution → ProjectConfig defaults
# ---------------------------------------------------------------------------


def _config_from_board(name: str, board_id: str) -> tuple[ProjectConfig, dict[str, Any]]:
    """Build a ProjectConfig + a render context from a board.json."""
    try:
        manifest = _boards.lookup(board_id)
    except BoardNotFoundError as exc:
        raise ScaffoldError(str(exc)) from exc

    payload = manifest.payload
    peripherals: list[PeripheralEntry] = []
    context: dict[str, Any] = {
        "target_label": (
            f"{manifest.summary.summary or manifest.board_id} "
            f"({manifest.vendor}/{manifest.family}/{manifest.device})"
        ).strip(),
        "has_debug_uart": False,
        "has_led": False,
    }

    debug_uart = payload.get("uart", {}).get("debug")
    if debug_uart and {"peripheral", "tx", "rx"} <= debug_uart.keys():
        peripheral_payload = {
            "kind": "uart",
            "name": "console",
            "peripheral": str(debug_uart["peripheral"]),
            "tx": str(debug_uart["tx"]),
            "rx": str(debug_uart["rx"]),
            "baud": int(debug_uart.get("baud", 115200)),
        }
        peripherals.append(
            PeripheralEntry(
                kind="uart",
                name="console",
                payload=peripheral_payload,
            )
        )
        context["has_debug_uart"] = True
        context["debug_uart_peripheral"] = peripheral_payload["peripheral"]
        context["debug_uart_tx"] = peripheral_payload["tx"]
        context["debug_uart_rx"] = peripheral_payload["rx"]

    leds = payload.get("leds") or []
    if leds and isinstance(leds[0], dict) and leds[0].get("pin"):
        led = leds[0]
        led_name = str(led.get("name") or "led")
        led_pin = str(led["pin"])
        peripherals.append(
            PeripheralEntry(
                kind="gpio",
                name=led_name,
                payload={
                    "kind": "gpio",
                    "name": led_name,
                    "pin": led_pin,
                    "mode": "output",
                    "initial": 0,
                },
            )
        )
        context["has_led"] = True
        context["led_pin"] = led_pin

    clocks: dict[str, Any] = {}
    profiles = payload.get("clock_profiles") or ()
    if profiles:
        clocks["profile"] = str(profiles[0])

    config = ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name=name, alloy_cli=_alloy_cli_version),
        board=BoardRef(id=manifest.board_id),
        chip=None,
        clocks=clocks,
        peripherals=tuple(peripherals),
        build={"profile": "debug"},
        flash={},
        raw={},
    )
    return config, context


def _config_from_device(
    name: str, device: tuple[str, str, str]
) -> tuple[ProjectConfig, dict[str, Any]]:
    vendor, family, dev = device
    try:
        ir = _ir.load_device(vendor, family, dev)
    except DeviceNotFoundError as exc:
        raise ScaffoldError(str(exc)) from exc

    config = ProjectConfig(
        schema_version=SCHEMA_VERSION,
        project=ProjectMeta(name=name, alloy_cli=_alloy_cli_version),
        board=None,
        chip=ChipRef(vendor=vendor, family=family, device=dev),
        clocks={},
        peripherals=(),
        build={"profile": "debug"},
        flash={},
        raw={},
    )
    label = ir.identity.summary or f"{vendor}/{family}/{dev}"
    context: dict[str, Any] = {
        "target_label": f"{label} (chip-only project)",
        "has_debug_uart": False,
        "has_led": False,
    }
    return config, context


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def _make_env() -> Environment:
    return Environment(
        loader=PackageLoader("alloy_cli", "templates"),
        autoescape=select_autoescape(default=False),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def _render(env: Environment, template: str, context: dict[str, Any]) -> str:
    return env.get_template(template).render(**context)


def _read_license_template(license_id: str) -> str:
    path = (
        resources.files("alloy_cli")
        .joinpath("templates")
        .joinpath("licenses")
        .joinpath(f"{license_id}.txt.j2")
    )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# scaffold()
# ---------------------------------------------------------------------------


def scaffold(req: ScaffoldRequest) -> ScaffoldResult:
    """Write a complete alloy-cli project tree to ``req.destination``."""
    _validate_request(req)

    if req.board_id is not None:
        config, board_context = _config_from_board(req.name, req.board_id)
    else:
        assert req.device is not None
        # The current scaffold expects [board] so the generated
        # CMakeLists can flow ALLOY_BOARD down to alloy/.  Chip-only
        # support needs a follow-up proposal that picks the board's
        # linker / startup metadata directly from a chip identifier.
        raise ScaffoldError(
            "alloy new --device (chip-only) is not yet wired through to "
            "the alloy HAL.  Pass --board <id> instead, or wait for the "
            "follow-up `wire-chip-only-projects` proposal."
        )

    dest = req.destination.resolve()
    _validate_destination(dest, force=req.force)
    dest.mkdir(parents=True, exist_ok=True)

    env = _make_env()
    year = _dt.date.today().year
    render_ctx: dict[str, Any] = {
        "project_name": req.name,
        "license": req.license,
        "author": req.author,
        "year": year,
        "alloy_cli_homepage": ALLOY_CLI_HOMEPAGE,
        **board_context,
    }

    files_written: list[Path] = []

    def _write(rel: str, body: str) -> None:
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        files_written.append(path)

    # 1. alloy.toml — round-tripped through core.project.write so it is
    #    schema-valid by construction and matches what `alloy add` will
    #    later regenerate.
    write(dest / PROJECT_FILE, config)
    files_written.append(dest / PROJECT_FILE)

    # 2. CMakeLists.txt
    _write("CMakeLists.txt", _render(env, "CMakeLists.txt.j2", render_ctx))

    # 3. src/main.cpp
    _write("src/main.cpp", _render(env, "main.cpp.j2", render_ctx))

    # 4. README.md
    _write("README.md", _render(env, "README.md.j2", render_ctx))

    # 5. .gitignore
    _write(".gitignore", _render(env, "gitignore.j2", render_ctx))

    # 6. LICENSE
    license_template = env.from_string(_read_license_template(req.license))
    _write("LICENSE", license_template.render(**render_ctx))

    return ScaffoldResult(
        name=req.name,
        destination=dest,
        files_written=tuple(sorted(files_written)),
        target_label=str(render_ctx["target_label"]),
        config=config,
    )


__all__ = [
    "ALLOY_CLI_HOMEPAGE",
    "PROJECT_NAME_RE",
    "SUPPORTED_LICENSES",
    "ScaffoldError",
    "ScaffoldRequest",
    "ScaffoldResult",
    "scaffold",
    "validate_project_name",
]
