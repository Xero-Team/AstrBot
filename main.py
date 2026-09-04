import argparse
import asyncio
import os
import sys

import runtime_bootstrap

runtime_bootstrap.initialize_runtime_bootstrap()

DASHBOARD_RESET_PASSWORD_ENV = "ASTRBOT_RESET_DASHBOARD_PASSWORD"


def _apply_startup_env_flags(argv: list[str]) -> None:
    """Apply startup flags that must take effect before core imports.

    Args:
        argv: Command-line arguments excluding the executable name.
    """

    if "-h" in argv or "--help" in argv:
        return

    startup_parser = argparse.ArgumentParser(add_help=False)
    startup_parser.add_argument("--reset-password", action="store_true")
    startup_args, _ = startup_parser.parse_known_args(argv)
    if startup_args.reset_password:
        os.environ[DASHBOARD_RESET_PASSWORD_ENV] = "1"


_apply_startup_env_flags(sys.argv[1:])

from astrbot.application import ApplicationOptions, run_application  # noqa: E402
from astrbot.runtime_instance_lock import RuntimeInstanceLockHeld  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstrBot")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help="Specify the directory path for WebUI static files",
        default=None,
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help=(
            "Reset the dashboard initial password on startup and print it in "
            "startup logs"
        ),
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_application(ApplicationOptions(webui_dir=args.webui_dir)))
    except RuntimeInstanceLockHeld:
        raise SystemExit(1) from None
