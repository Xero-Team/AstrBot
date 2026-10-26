"""AstrBot CLI entry point."""

from __future__ import annotations

from importlib import import_module

import click

import runtime_bootstrap

from . import __version__

runtime_bootstrap.initialize_runtime_bootstrap()


class LazyCommandGroup(click.Group):
    """Resolve command modules only after process bootstrap has completed."""

    _commands = {
        "conf": ("astrbot.cli.commands.cmd_conf", "conf"),
        "init": ("astrbot.cli.commands.cmd_init", "init"),
        "install-browser": (
            "astrbot.cli.commands.cmd_install_browser",
            "install_browser",
        ),
        "password": ("astrbot.cli.commands.cmd_password", "password"),
        "plug": ("astrbot.cli.commands.cmd_plug", "plug"),
        "run": ("astrbot.cli.commands.cmd_run", "run"),
    }

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *self._commands})

    def get_command(self, ctx: click.Context, cmd_name: str):
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        module_name, attribute = self._commands.get(cmd_name, (None, None))
        if module_name is None or attribute is None:
            return None
        return getattr(import_module(module_name), attribute)


_LOGO = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|
"""


@click.group(cls=LazyCommandGroup)
@click.version_option(__version__, prog_name="AstrBot")
def cli() -> None:
    """The AstrBot CLI."""
    click.echo(_LOGO)
    click.echo("Welcome to AstrBot CLI!")
    click.echo(f"AstrBot CLI version: {__version__}")


@click.command(name="help")
@click.argument("command_name", required=False, type=str)
def help_command(command_name: str | None) -> None:
    """Display help information for commands."""
    ctx = click.get_current_context()
    if command_name:
        command = cli.get_command(ctx, command_name)
        if command:
            click.echo(command.get_help(ctx))
        else:
            click.echo(f"Unknown command: {command_name}")
            raise SystemExit(1)
    else:
        click.echo(cli.get_help(ctx))


cli.add_command(help_command)

if __name__ == "__main__":
    cli()
