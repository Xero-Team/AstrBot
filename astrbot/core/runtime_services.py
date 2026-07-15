"""Explicitly constructed runtime-owned services.

Importing this module only defines the factory; it does not touch user data,
create directories, start schedulers, or configure logging.
"""

import os
from dataclasses import dataclass

from astrbot import logger
from astrbot.core.config import AstrBotConfig
from astrbot.core.config.default import DB_PATH
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.file_token_service import FileTokenService
from astrbot.core.log import LogManager
from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.t2i.renderer import HtmlRenderer


@dataclass(slots=True)
class RuntimeServices:
    """Services owned by one AstrBot runtime instance."""

    config: AstrBotConfig
    db: SQLiteDatabase
    preferences: SharedPreferences
    html_renderer: HtmlRenderer
    file_token_service: FileTokenService
    pip_installer: PipInstaller
    demo_mode: bool


def create_runtime_services() -> RuntimeServices:
    """Create runtime services after the process environment has been prepared."""
    config = AstrBotConfig()
    LogManager.configure_logger(logger, config)
    LogManager.configure_trace_logger(config)
    db = SQLiteDatabase(DB_PATH)
    return RuntimeServices(
        config=config,
        db=db,
        preferences=SharedPreferences(db_helper=db),
        html_renderer=HtmlRenderer(),
        file_token_service=FileTokenService(),
        pip_installer=PipInstaller(
            config.get("pip_install_arg", ""),
            config.get("pypi_index_url", None),
        ),
        demo_mode=os.getenv("DEMO_MODE", "False").strip().lower() in ("true", "1", "t"),
    )
