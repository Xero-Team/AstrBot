import asyncio
import os
import sys

import click

from ..utils.basic import check_astrbot_root, get_astrbot_root

DASHBOARD_RESET_PASSWORD_ENV = "ASTRBOT_RESET_DASHBOARD_PASSWORD"


async def _run_application() -> None:
    """Import the shared runner only after runtime bootstrap has completed."""
    from astrbot.application import ApplicationOptions, run_application

    await run_application(ApplicationOptions())


def _initialize_runtime_bootstrap() -> None:
    """Install the verified aiohttp CA context before importing core modules."""
    import runtime_bootstrap

    runtime_bootstrap.initialize_runtime_bootstrap()


@click.option("--reload", "-r", is_flag=True, help="Auto-reload plugins")
@click.option("--port", "-p", help="AstrBot Dashboard port", required=False, type=str)
@click.option(
    "--reset-password",
    is_flag=True,
    help="Reset dashboard initial password on startup",
)
@click.command()
def run(reload: bool, port: str | None, reset_password: bool) -> None:
    """Run AstrBot"""
    try:
        os.environ["ASTRBOT_CLI"] = "1"
        astrbot_root = get_astrbot_root()

        if not check_astrbot_root(astrbot_root):
            raise click.ClickException(
                f"{astrbot_root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize",
            )

        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        sys.path.insert(0, str(astrbot_root))

        _initialize_runtime_bootstrap()

        if port:
            os.environ["DASHBOARD_PORT"] = port

        if reload:
            click.echo("Plugin auto-reload enabled")
            os.environ["ASTRBOT_RELOAD"] = "1"

        if reset_password:
            os.environ[DASHBOARD_RESET_PASSWORD_ENV] = "1"

        asyncio.run(_run_application())
    except KeyboardInterrupt:
        click.echo("AstrBot has been shut down.")
    except click.ClickException:
        raise
    except Exception as exc:
        # Runtime startup errors now propagate from the shared application
        # runner.  Do not echo exception text or tracebacks here: this command
        # must stay outside the Core import boundary, and either can contain
        # credentials or private endpoint details.  Startup paths log redacted
        # diagnostics before propagating failures.
        raise click.ClickException(
            "Runtime failed. See AstrBot logs for details."
        ) from exc
