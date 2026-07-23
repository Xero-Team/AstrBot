from typing import Any, Protocol, cast

from astrbot import logger
from astrbot.core.platform.catalog import PlatformCatalog
from astrbot.core.platform.discovery import discover_platform_adapter
from astrbot.core.platform.provisioning import PlatformProvisioningValidationError


class PlatformServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class WebhookPlatformAdapter(Protocol):
    config: dict[str, Any]

    def meta(self) -> Any: ...

    async def webhook_callback(self, request_obj) -> Any: ...


class PlatformManagerPort(Protocol):
    """Platform operations exposed to Dashboard transport services."""

    def find_inst_by_webhook_uuid(self, webhook_uuid: str) -> object | None: ...

    def get_all_stats(self) -> dict: ...

    async def invoke_action(
        self,
        platform_id: str,
        action_name: str,
        **kwargs: Any,
    ) -> dict: ...


class PlatformService:
    """Dashboard operations over injected platform runtime capabilities."""

    def __init__(
        self,
        platform_manager: PlatformManagerPort,
        platform_catalog: PlatformCatalog,
    ) -> None:
        self.platform_manager = platform_manager
        self.platform_catalog = platform_catalog

    async def handle_webhook_callback(self, webhook_uuid: str, request_obj):
        platform_adapter = self.find_platform_by_uuid(webhook_uuid)

        if not platform_adapter:
            logger.warning(f"未找到 webhook_uuid 为 {webhook_uuid} 的平台")
            raise PlatformServiceError("未找到对应平台", 404)

        platform_adapter = cast(WebhookPlatformAdapter, platform_adapter)

        try:
            return await platform_adapter.webhook_callback(request_obj)
        except NotImplementedError as exc:
            logger.error(
                f"平台 {platform_adapter.meta().name} 未实现 webhook_callback 方法"
            )
            raise PlatformServiceError("平台未支持统一 Webhook 模式", 500) from exc
        except Exception as exc:
            logger.error(f"处理 webhook 回调时发生错误: {exc}", exc_info=True)
            raise PlatformServiceError("处理回调失败", 500) from exc

    def find_platform_by_uuid(self, webhook_uuid: str) -> object | None:
        return self.platform_manager.find_inst_by_webhook_uuid(webhook_uuid)

    def get_platform_stats(self):
        try:
            return self.platform_manager.get_all_stats()
        except Exception as exc:
            logger.error(f"获取平台统计信息失败: {exc}", exc_info=True)
            raise PlatformServiceError(f"获取统计信息失败: {exc}", 500) from exc

    async def invoke_platform_action(
        self,
        platform_id: str,
        action_name: str,
        payload: dict | None = None,
    ) -> dict:
        normalized_action = str(action_name).strip()
        if not normalized_action:
            raise PlatformServiceError("Missing action_name", 400)
        if payload is not None and not isinstance(payload, dict):
            raise PlatformServiceError("Payload must be an object", 400)

        try:
            return await self.platform_manager.invoke_action(
                platform_id,
                normalized_action,
                **(payload or {}),
            )
        except LookupError as exc:
            raise PlatformServiceError(str(exc), 404) from exc
        except NotImplementedError as exc:
            raise PlatformServiceError(str(exc), 400) from exc
        except ValueError as exc:
            raise PlatformServiceError(str(exc), 400) from exc
        except TypeError as exc:
            raise PlatformServiceError(f"Invalid action payload: {exc}", 400) from exc
        except Exception as exc:
            logger.error(
                "执行平台动作失败: platform_id=%s action=%s error=%s",
                platform_id,
                normalized_action,
                exc,
                exc_info=True,
            )
            raise PlatformServiceError("平台动作执行失败", 500) from exc

    async def handle_platform_registration(
        self,
        platform_type: str,
        payload: dict,
    ) -> dict:
        try:
            action = str(payload.get("action", "")).strip().lower()
            if not action:
                raise PlatformServiceError("Missing action", 400)

            platform_config = payload.get("platform_config")
            if not isinstance(platform_config, dict):
                platform_config = {}

            registration = self.platform_catalog.get(platform_type)
            if registration is None:
                discover_platform_adapter(platform_type, self.platform_catalog)
                registration = self.platform_catalog.get(platform_type)
            if registration is None or registration.descriptor.provisioner is None:
                raise PlatformServiceError(
                    f"Unsupported platform registration: {platform_type}",
                    404,
                )

            return await registration.descriptor.provisioner(
                action=action,
                payload=payload,
                platform_config=platform_config,
            )
        except PlatformServiceError:
            raise
        except PlatformProvisioningValidationError as exc:
            raise PlatformServiceError(str(exc), 400) from exc
        except Exception as exc:
            logger.error(f"处理平台一键创建请求失败: {exc}", exc_info=True)
            raise PlatformServiceError(str(exc), 500) from exc
