"""``alloy export <kind>`` — emit auxiliary configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alloy_cli.core.errors import (
    BoardNotFoundError,
    DataRepoMissingError,
    DeviceNotFoundError,
)
from alloy_cli.core.project import ProjectConfig

# ---------------------------------------------------------------------------
# Toolchain selection
# ---------------------------------------------------------------------------


def _core_from_device_name(device: str) -> str:
    """Best-effort heuristic when an IR lookup isn't available.

    The exhaustive list lives in alloy-devices-yml — this is just
    the safety net so the workflow emitter always has *something*.
    """
    name = device.lower()
    if "riscv" in name or name.startswith(("esp32-c", "esp32-h", "esp32-p", "ch32")):
        return "riscv"
    if name.startswith(("esp32-s", "esp32")):
        # esp32 / esp32-s* are Xtensa.  Note the ordering: -c / -h /
        # -p variants matched the RISC-V branch first.
        return "xtensa"
    return "cortex-m"  # ARM default — covers stm32, nrf, sam, rp2040.


def _detect_core(config: ProjectConfig) -> str:
    """Resolve the active core ID from the project config.

    Preference order:
    1. IR `identity.core` (most accurate).
    2. Device-name prefix heuristic (works offline / on bulk
       devices that haven't been admitted yet).
    3. Empty string when neither chip nor board is set; the
       caller treats that as "fall back to ARM".
    """
    from alloy_cli.core.ir import load_device

    if config.chip is not None:
        try:
            ir = load_device(
                vendor=config.chip.vendor,
                family=config.chip.family,
                device=config.chip.device,
            )
        except (DeviceNotFoundError, DataRepoMissingError):
            return _core_from_device_name(config.chip.device)
        return ir.identity.core or _core_from_device_name(config.chip.device)
    if config.board is not None:
        from alloy_cli.core import boards as _boards

        try:
            manifest = _boards.lookup(config.board.id)
            ir = load_device(manifest.vendor, manifest.family, manifest.device)
        except (BoardNotFoundError, DeviceNotFoundError, DataRepoMissingError):
            return ""
        return ir.identity.core or _core_from_device_name(manifest.device)
    return ""


def _toolchain_step(core: str) -> str:
    """Return the YAML snippet that installs the right cross-compile toolchain."""
    core = (core or "").lower()
    if "riscv" in core or core.startswith("rv"):
        # apt-get because there isn't a stable GH Action for the
        # RISC-V toolchain; the package matrix Ubuntu ships covers
        # the breadth we need (gcc-riscv64-unknown-elf).
        return (
            "      - name: Install RISC-V GCC\n"
            "        run: |\n"
            "          sudo apt-get update -qq\n"
            "          sudo apt-get install -y --no-install-recommends gcc-riscv64-unknown-elf\n"
        )
    if "xtensa" in core or core.startswith("esp"):
        return (
            "      - name: Setup Xtensa toolchain (ESP-IDF)\n"
            "        uses: espressif/install-esp-idf-action@v1\n"
            "        with: { esp_idf_version: v5.1 }\n"
        )
    # Default: ARM.  carlosperate/arm-none-eabi-gcc-action is the
    # canonical maintainer-blessed action for embedded ARM CI.
    return (
        "      - name: Setup arm-none-eabi-gcc\n"
        "        uses: carlosperate/arm-none-eabi-gcc-action@v1\n"
        "        with: { release: latest }\n"
    )


# ---------------------------------------------------------------------------
# CI workflows
# ---------------------------------------------------------------------------


def github_workflow(config: ProjectConfig) -> str:
    """Emit a matrix-aware GitHub Actions workflow.

    The workflow installs the right cross-compile toolchain
    (arm-none-eabi-gcc / RISC-V / Xtensa), runs a debug + release
    matrix, caches alloy-cli's pip dir per ``alloy.toml`` SHA, and
    appends an ``alloy doctor --json`` step gated on
    ``if: failure()`` so the captured log surfaces actionable
    install hints when something goes sideways.
    """
    core = _detect_core(config)
    toolchain_step = _toolchain_step(core)
    profile_default = config.build.get("profile", "release")
    return (
        "name: firmware\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "    branches: [main]\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy:\n"
        "      fail-fast: false\n"
        "      matrix:\n"
        "        profile: [debug, release]\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          submodules: recursive\n"
        "          fetch-depth: 0\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.12'\n"
        "          cache: pip\n"
        f"{toolchain_step}"
        "      - name: Cache alloy state\n"
        "        uses: actions/cache@v4\n"
        "        with:\n"
        "          path: .alloy/cache\n"
        "          key: alloy-${{ hashFiles('alloy.toml', '.alloy/version.lock') }}\n"
        "      - name: Install alloy-cli\n"
        "        run: pip install alloy-cli\n"
        "      - name: Build (${{ matrix.profile }})\n"
        f"        run: alloy build --profile ${{{{ matrix.profile }}}}\n"
        "      - name: Upload firmware artifact\n"
        "        if: success()\n"
        "        uses: actions/upload-artifact@v4\n"
        "        with:\n"
        f"          name: firmware-${{{{ matrix.profile }}}}\n"
        "          path: |\n"
        "            .alloy/build/*.elf\n"
        "            .alloy/build/*.map\n"
        "          retention-days: 14\n"
        "      - name: Diagnose on failure\n"
        "        if: failure()\n"
        "        run: alloy doctor --json\n"
        f"# alloy.toml profile default: {profile_default}\n"
    )


def gitlab_workflow(config: ProjectConfig) -> str:
    return (
        "stages: [build]\n"
        "build:\n"
        "  stage: build\n"
        "  image: python:3.12\n"
        "  before_script:\n"
        "    - pip install alloy-cli\n"
        "  script:\n"
        f"    - alloy build --profile {config.build.get('profile', 'release')}\n"
    )


def jenkins_workflow(config: ProjectConfig) -> str:
    return (
        "pipeline {\n"
        "  agent any\n"
        "  stages {\n"
        "    stage('build') {\n"
        "      steps {\n"
        "        sh 'pip install alloy-cli'\n"
        f"        sh 'alloy build --profile {config.build.get('profile', 'release')}'\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# VS Code
# ---------------------------------------------------------------------------


def vscode_launch_json(config: ProjectConfig) -> dict[str, Any]:
    elf = f"${{workspaceFolder}}/.alloy/build/{config.project.name}.elf"
    return {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "alloy debug",
                "type": "cortex-debug",
                "request": "launch",
                "servertype": "external",
                "executable": elf,
                "cwd": "${workspaceFolder}",
                "preLaunchTask": "alloy build",
            }
        ],
    }


def vscode_tasks_json(_config: ProjectConfig) -> dict[str, Any]:
    return {
        "version": "2.0.0",
        "tasks": [
            {
                "label": "alloy build",
                "type": "shell",
                "command": "alloy",
                "args": ["build"],
                "group": {"kind": "build", "isDefault": True},
            },
            {
                "label": "alloy flash",
                "type": "shell",
                "command": "alloy",
                "args": ["flash"],
            },
            {
                "label": "alloy debug",
                "type": "shell",
                "command": "alloy",
                "args": ["debug"],
            },
        ],
    }


def vscode_c_cpp_properties(_config: ProjectConfig) -> dict[str, Any]:
    return {
        "version": 4,
        "configurations": [
            {
                "name": "alloy",
                "includePath": [
                    "${workspaceFolder}/src",
                    "${workspaceFolder}/.alloy/generated/include",
                ],
                "defines": [],
                "cStandard": "c17",
                "cppStandard": "c++20",
                "intelliSenseMode": "linux-gcc-arm",
            }
        ],
    }


# ---------------------------------------------------------------------------
# GDB / BOM
# ---------------------------------------------------------------------------


def gdbinit(config: ProjectConfig) -> str:
    elf = f".alloy/build/{config.project.name}.elf"
    return (
        "# alloy-cli generated .gdbinit\n"
        f"file {elf}\n"
        "target extended-remote :1337\n"
        "set print pretty on\n"
        "set pagination off\n"
    )


def bill_of_materials(config: ProjectConfig) -> dict[str, Any]:
    chip = (
        {
            "vendor": config.chip.vendor,
            "family": config.chip.family,
            "device": config.chip.device,
        }
        if config.chip
        else None
    )
    board = {"id": config.board.id} if config.board else None
    return {
        "schema_version": "1.0",
        "project": {"name": config.project.name},
        "chip": chip,
        "board": board,
        "peripherals": [{"kind": p.kind, "name": p.name} for p in config.peripherals],
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def emit(kind: str, config: ProjectConfig, *, target: str | None = None) -> dict[Path, str]:
    """Return a mapping ``relative path → file contents`` for the requested kind."""
    if kind == "ci":
        sub = (target or "github").lower()
        if sub == "github":
            return {Path(".github/workflows/firmware.yml"): github_workflow(config)}
        if sub == "gitlab":
            return {Path(".gitlab-ci.yml"): gitlab_workflow(config)}
        if sub == "jenkins":
            return {Path("Jenkinsfile"): jenkins_workflow(config)}
        raise ValueError(f"Unknown CI target {target!r}.")
    if kind == "vscode":
        import json

        return {
            Path(".vscode/launch.json"): json.dumps(vscode_launch_json(config), indent=2) + "\n",
            Path(".vscode/tasks.json"): json.dumps(vscode_tasks_json(config), indent=2) + "\n",
            Path(".vscode/c_cpp_properties.json"): json.dumps(
                vscode_c_cpp_properties(config), indent=2
            )
            + "\n",
        }
    if kind == "gdb":
        return {Path(".gdbinit"): gdbinit(config)}
    if kind == "bom":
        import json

        return {Path("bom.json"): json.dumps(bill_of_materials(config), indent=2) + "\n"}
    raise ValueError(f"Unknown export kind {kind!r}.")


__all__ = [
    "bill_of_materials",
    "emit",
    "gdbinit",
    "github_workflow",
    "gitlab_workflow",
    "jenkins_workflow",
    "vscode_c_cpp_properties",
    "vscode_launch_json",
    "vscode_tasks_json",
]
