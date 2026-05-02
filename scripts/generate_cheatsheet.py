"""Render a single-page CLI cheatsheet from the live Click tree.

Run::

    python scripts/generate_cheatsheet.py            # rewrite docs/CHEATSHEET.md
    python scripts/generate_cheatsheet.py --check    # CI-friendly drift check

The output is the canonical reference for ``alloy <subcommand>``;
because it walks the Click tree at runtime it can't drift from
the actual CLI surface.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ruff: noqa: E402
from alloy_cli.main import cli  # type: ignore[import]

_TARGET = _REPO_ROOT / "docs" / "CHEATSHEET.md"


def _walk(group: click.Group, prefix: str = "alloy") -> list[tuple[str, click.Command]]:
    out: list[tuple[str, click.Command]] = []
    for name in sorted(group.commands):
        cmd = group.commands[name]
        full = f"{prefix} {name}"
        if isinstance(cmd, click.Group):
            out.extend(_walk(cmd, full))
        else:
            out.append((full, cmd))
    return out


def _format_options(cmd: click.Command) -> list[str]:
    rows: list[str] = []
    for param in cmd.params:
        if not isinstance(param, click.Option):
            continue
        flags = ", ".join(param.opts + param.secondary_opts)
        help_text = (param.help or "").replace("\n", " ").strip()
        if param.required:
            help_text = f"**required.** {help_text}"
        rows.append(f"  - `{flags}` — {help_text}")
    return rows


def render() -> str:
    lines: list[str] = [
        "# alloy-cli — cheatsheet",
        "",
        "Auto-generated from the live Click command tree.  Run "
        "`python scripts/generate_cheatsheet.py` after adding or "
        "renaming a subcommand.",
        "",
    ]
    for full_name, cmd in _walk(cli):
        help_text = (cmd.help or "").splitlines()[0].strip() if cmd.help else ""
        lines.append(f"## `{full_name}`")
        lines.append("")
        if help_text:
            lines.append(help_text)
            lines.append("")
        opts = _format_options(cmd)
        if opts:
            lines.append("Options:")
            lines.extend(opts)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when CHEATSHEET.md would drift; CI uses this.",
    )
    args = parser.parse_args()

    expected = render()
    if args.check:
        actual = _TARGET.read_text(encoding="utf-8") if _TARGET.exists() else ""
        if actual != expected:
            print(
                "::error::docs/CHEATSHEET.md is stale.  Re-run "
                "`python scripts/generate_cheatsheet.py` and commit "
                "the diff.",
                file=sys.stderr,
            )
            sys.exit(1)
        print("CHEATSHEET.md up to date.")
        return

    _TARGET.parent.mkdir(parents=True, exist_ok=True)
    _TARGET.write_text(expected, encoding="utf-8")
    print(f"  ✓ {_TARGET.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
