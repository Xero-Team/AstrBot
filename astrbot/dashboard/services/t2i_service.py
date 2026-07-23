from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.core_runtime import CoreControl
from astrbot.core.utils.t2i.template_manager import TemplateManager


class T2iServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class T2iService:
    def __init__(
        self,
        config: AstrBotConfig,
        config_manager: AstrBotConfigManager,
        core_control: CoreControl,
        manager: TemplateManager | None = None,
    ) -> None:
        self.config_manager = config_manager
        self.core_control = core_control
        self.config = config
        self.manager = manager or TemplateManager()

    async def reload_all_pipeline_schedulers(self) -> None:
        for conf_id in self.config_manager.confs:
            await self.core_control.reload_pipeline_scheduler(conf_id)

    async def sync_active_template_to_all_configs(self, name: str) -> None:
        for config in self.config_manager.confs.values():
            committed = await config.save_config_async({"t2i_active_template": name})
            if not committed:
                raise T2iServiceError(
                    "T2I template configuration save was superseded by a newer update."
                )
        await self.reload_all_pipeline_schedulers()

    def list_templates(self):
        try:
            return self.manager.list_templates()
        except Exception as exc:
            raise T2iServiceError(str(exc)) from exc

    def get_active_template(self) -> dict:
        try:
            return {"active_template": self.config.get("t2i_active_template", "base")}
        except Exception as exc:
            logger.error("Error in get_active_template", exc_info=True)
            raise T2iServiceError(str(exc)) from exc

    def get_template(self, name: str) -> dict:
        try:
            return {"name": name, "content": self.manager.get_template(name)}
        except FileNotFoundError as exc:
            raise T2iServiceError("Template not found", 404) from exc
        except Exception as exc:
            raise T2iServiceError(str(exc)) from exc

    def create_template(self, name: str | None, content: str | None) -> dict:
        if not name or not content:
            raise T2iServiceError("Name and content are required.", 400)

        name = name.strip()
        try:
            self.manager.create_template(name, content)
        except FileExistsError as exc:
            raise T2iServiceError(
                "Template with this name already exists.",
                409,
            ) from exc
        except ValueError as exc:
            raise T2iServiceError(str(exc), 400) from exc
        except Exception as exc:
            raise T2iServiceError(str(exc)) from exc

        return {"name": name}

    async def update_template(self, name: str, content: str | None) -> tuple[dict, str]:
        name = name.strip()
        if content is None:
            raise T2iServiceError("Content is required.", 400)

        try:
            self.manager.update_template(name, content)
            active_template = self.config.get("t2i_active_template", "base")
            if name == active_template:
                await self.reload_all_pipeline_schedulers()
                message = f"模板 '{name}' 已更新并重新加载。"
            else:
                message = f"模板 '{name}' 已更新。"
        except ValueError as exc:
            raise T2iServiceError(str(exc), 400) from exc
        except Exception as exc:
            raise T2iServiceError(str(exc)) from exc

        return {"name": name}, message

    def delete_template(self, name: str) -> None:
        name = name.strip()
        try:
            self.manager.delete_template(name)
        except FileNotFoundError as exc:
            raise T2iServiceError("Template not found.", 404) from exc
        except ValueError as exc:
            raise T2iServiceError(str(exc), 400) from exc
        except Exception as exc:
            raise T2iServiceError(str(exc)) from exc

    async def set_active_template(self, name: str | None) -> str:
        if not name:
            raise T2iServiceError("模板名称(name)不能为空。", 400)

        try:
            self.manager.get_template(name)
            await self.sync_active_template_to_all_configs(name)
        except FileNotFoundError as exc:
            raise T2iServiceError(f"模板 '{name}' 不存在，无法应用。", 404) from exc
        except Exception as exc:
            logger.error("Error in set_active_template", exc_info=True)
            raise T2iServiceError(str(exc)) from exc

        return f"模板 '{name}' 已成功应用。"

    async def reset_default_template(self) -> str:
        try:
            self.manager.reset_default_template()
            await self.sync_active_template_to_all_configs("base")
        except FileNotFoundError as exc:
            raise T2iServiceError(str(exc), 404) from exc
        except Exception as exc:
            logger.error("Error in reset_default_template", exc_info=True)
            raise T2iServiceError(str(exc)) from exc

        return "Default template has been reset and activated."
