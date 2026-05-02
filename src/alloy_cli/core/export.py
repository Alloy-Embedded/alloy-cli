"""``alloy export <kind>`` — emit auxiliary configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alloy_cli.core.project import ProjectConfig

# ---------------------------------------------------------------------------
# CI workflows
# ---------------------------------------------------------------------------


def github_workflow(config: ProjectConfig) -> str:
    return (
        "name: build\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-python@v5\n"
        "        with: { python-version: '3.12' }\n"
        f"      - run: pip install alloy-cli\n"
        f"      - run: alloy build --profile {config.build.get('profile', 'release')}\n"
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
            return {Path(".github/workflows/build.yml"): github_workflow(config)}
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
