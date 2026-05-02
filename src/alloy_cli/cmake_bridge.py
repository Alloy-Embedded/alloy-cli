"""CMake bridge — reads ``alloy.toml`` and emits a flat JSON manifest.

Used from CMake via::

    execute_process(
      COMMAND ${Python3_EXECUTABLE} -m alloy_cli.cmake_bridge
              --project-dir ${CMAKE_SOURCE_DIR}
              --emit-json
      OUTPUT_VARIABLE ALLOY_MANIFEST_JSON
    )
    string(JSON ALLOY_BOARD_ID GET "${ALLOY_MANIFEST_JSON}" board id)

The output is intentionally flat and JSON — CMake's ``string(JSON ...)``
parser is fine with nested objects but every project's ``CMakeLists.txt``
should be able to read what it needs without writing helper macros.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from alloy_cli.core.errors import AlloyCliError
from alloy_cli.core.project import PROJECT_FILE, ProjectConfig, read

# ---------------------------------------------------------------------------
# Manifest projection
# ---------------------------------------------------------------------------


def project_manifest(config: ProjectConfig) -> dict[str, Any]:
    """Project a :class:`ProjectConfig` to the JSON manifest CMake reads."""
    manifest: dict[str, Any] = {
        "schema_version": config.schema_version,
        "project": {"name": config.project.name},
    }
    if config.project.alloy_cli is not None:
        manifest["project"]["alloy-cli"] = config.project.alloy_cli
    if config.project.alloy is not None:
        manifest["project"]["alloy"] = config.project.alloy
    if config.project.alloy_codegen is not None:
        manifest["project"]["alloy-codegen"] = config.project.alloy_codegen
    if config.project.alloy_devices_yml is not None:
        manifest["project"]["alloy-devices-yml"] = config.project.alloy_devices_yml

    if config.board is not None:
        manifest["board"] = {"id": config.board.id}
    if config.chip is not None:
        manifest["chip"] = {
            "vendor": config.chip.vendor,
            "family": config.chip.family,
            "device": config.chip.device,
        }
    if config.clocks:
        manifest["clocks"] = dict(config.clocks)
    if config.peripherals:
        manifest["peripherals"] = [dict(p.payload) for p in config.peripherals]
    if config.build:
        manifest["build"] = dict(config.build)
    if config.flash:
        manifest["flash"] = dict(config.flash)

    return manifest


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m alloy_cli.cmake_bridge",
        description="Emit a JSON manifest for CMake from alloy.toml.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing alloy.toml (defaults to CWD).",
    )
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="Print the manifest JSON to stdout (default behaviour).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=None,
        help="Pretty-print JSON with the given indent.  Default: compact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    toml_path = args.project_dir / PROJECT_FILE
    try:
        config = read(toml_path)
    except AlloyCliError as exc:
        # CMake will surface stderr; keep it terse and machine-friendly.
        print(f"alloy_cli.cmake_bridge: {exc}", file=sys.stderr)
        return 2

    manifest = project_manifest(config)
    json.dump(manifest, sys.stdout, indent=args.indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via the script entry
    raise SystemExit(main())
