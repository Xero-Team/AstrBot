import inspect
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from astrbot import logger
from astrbot.core.utils.error_redaction import redact_sensitive_text
from astrbot.core.utils.pip_installer import PipInstaller


async def call_pip_install(pip_installer: PipInstaller, *args, **kwargs):
    result = pip_installer.install(*args, **kwargs)
    if inspect.isawaitable(result):
        return await cast(Awaitable[Any], result)
    return result


@dataclass
class PipInstallResult:
    data: Any = None
    message: str | None = None
    status: str = "ok"
    headers: dict | None = None


class PipInstallServiceError(Exception):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class PipInstallService:
    def __init__(
        self,
        *,
        pip_install_func: Callable[..., Awaitable[Any]],
        demo_mode: bool,
    ) -> None:
        self.pip_install = pip_install_func
        self.demo_mode = demo_mode

    async def install_pip_package(self, data: object) -> PipInstallResult:
        if self.demo_mode:
            raise PipInstallServiceError(
                "You are not permitted to do this operation in demo mode"
            )

        payload = data if isinstance(data, dict) else {}
        package = payload.get("package", "")
        mirror = payload.get("mirror", None)
        if not package:
            raise PipInstallServiceError("缺少参数 package 或不合法。")
        try:
            await self.pip_install(package, mirror=mirror)
            return PipInstallResult(message="安装成功。")
        except Exception as exc:
            logger.error(
                "/api/v1/pip/install: %s",
                redact_sensitive_text(traceback.format_exc()),
            )
            raise PipInstallServiceError("安装依赖失败。") from exc
