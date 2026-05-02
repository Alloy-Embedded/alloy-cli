"""``alloy`` CLI entry point.

The Click root command + global options.  Subcommands land via
later proposals (``add-cli-new``, ``add-cli-build-flash-debug``,
``add-cli-boards-and-devices``, ``add-cli-add-peripheral``,
``add-mcp-server``, ``add-doctor-update-export``).

This module ships only:

* ``alloy --version`` — version string from VCS tags via hatch-vcs.
* ``alloy --help`` — banner mentioning the Alloy embedded platform.

Everything else routes through subcommand groups that future
proposals add via ``cli.add_command(...)``.
"""

from __future__ import annotations

import sys
from typing import NoReturn

import click
from rich.console import Console

from alloy_cli import __version__
from alloy_cli.commands.add import add_command
from alloy_cli.commands.boards import boards_command
from alloy_cli.commands.build import build_command
from alloy_cli.commands.chat import chat_command
from alloy_cli.commands.debug import debug_command
from alloy_cli.commands.devices import devices_command
from alloy_cli.commands.doctor import doctor_command
from alloy_cli.commands.export import export_command
from alloy_cli.commands.flash import flash_command
from alloy_cli.commands.mcp import mcp_command
from alloy_cli.commands.new import new_command
from alloy_cli.commands.toolchain import toolchain_command
from alloy_cli.commands.ui import ui_command
from alloy_cli.commands.update import update_command

_BANNER = """\
alloy — terminal-native developer surface for the Alloy embedded platform.

The roadmap is sequenced under openspec/changes/ in this repository.
Phase 1 (this proposal: bootstrap-alloy-cli) ships only the package
skeleton.  Subcommands (new, build, flash, debug, boards, add, mcp,
doctor) land in subsequent proposals.
"""


@click.group(
    invoke_without_command=True,
    help=_BANNER,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(
    version=__version__,
    package_name="alloy-cli",
    prog_name="alloy",
    message="%(prog)s %(version)s",
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """alloy — Alloy embedded platform CLI."""
    if ctx.invoked_subcommand is None:
        # No subcommand: print the banner via Rich for nice colors,
        # then the standard Click usage line.
        Console().print(_BANNER)
        click.echo(ctx.get_usage())


cli.add_command(new_command)
cli.add_command(build_command)
cli.add_command(flash_command)
cli.add_command(debug_command)
cli.add_command(boards_command)
cli.add_command(devices_command)
cli.add_command(add_command)
cli.add_command(ui_command)
cli.add_command(mcp_command)
cli.add_command(chat_command)
cli.add_command(doctor_command)
cli.add_command(toolchain_command)
cli.add_command(update_command)
cli.add_command(export_command)


def main(argv: list[str] | None = None) -> NoReturn:
    """``[project.scripts] alloy = "alloy_cli.main:main"`` entry."""
    try:
        cli.main(args=argv, prog_name="alloy", standalone_mode=False)
    except click.exceptions.UsageError as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.exceptions.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.stderr.write("\nInterrupted.\n")
        sys.exit(130)
    sys.exit(0)


if __name__ == "__main__":
    main()
