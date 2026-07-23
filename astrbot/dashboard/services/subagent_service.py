import copy
import traceback

from astrbot import logger
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.core.tools.function_tool_manager import FunctionToolManager


class SubAgentServiceError(Exception):
    pass


class SubAgentService:
    def __init__(
        self,
        config: AstrBotConfig,
        subagent_orchestrator: SubAgentOrchestrator,
        tool_manager: FunctionToolManager,
    ) -> None:
        self.config = config
        self.subagent_orchestrator = subagent_orchestrator
        self.tool_manager = tool_manager

    def get_config(self) -> dict:
        try:
            config_data = self.config.get("subagent_orchestrator")
            return self._normalize_config(config_data)
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SubAgentServiceError(f"获取 subagent 配置失败: {exc!s}") from exc

    async def update_config(self, data: object) -> None:
        try:
            if not isinstance(data, dict):
                raise SubAgentServiceError("配置必须为 JSON 对象")

            next_config = copy.deepcopy(data)
            committed = await self.config.save_config_async(
                {"subagent_orchestrator": next_config},
            )
            if not committed:
                raise SubAgentServiceError(
                    "Subagent configuration save was superseded by a newer update."
                )
            await self.subagent_orchestrator.reload_from_config(next_config)
        except SubAgentServiceError:
            raise
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SubAgentServiceError(f"保存 subagent 配置失败: {exc!s}") from exc

    def get_available_tools(self) -> list[dict]:
        try:
            tools = []
            for tool in self.tool_manager.func_list:
                if self._is_subagent_internal_tool(tool):
                    continue
                tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                        "active": tool.active,
                        "handler_module_path": tool.handler_module_path,
                    }
                )
            return tools
        except Exception as exc:
            logger.error(traceback.format_exc())
            raise SubAgentServiceError(f"获取可用工具失败: {exc!s}") from exc

    @staticmethod
    def _normalize_config(data: object) -> dict:
        if not isinstance(data, dict):
            data = {
                "main_enable": False,
                "remove_main_duplicate_tools": False,
                "agents": [],
            }

        data.setdefault("main_enable", False)
        data.setdefault("remove_main_duplicate_tools", False)
        data.setdefault("agents", [])

        agents = data.get("agents")
        if isinstance(agents, list):
            for agent in agents:
                if isinstance(agent, dict):
                    agent.setdefault("provider_id", None)
                    agent.setdefault("persona_id", None)

        return data

    @staticmethod
    def _is_subagent_internal_tool(tool) -> bool:
        return (
            isinstance(tool, HandoffTool)
            or tool.handler_module_path == "core.subagent_orchestrator"
        )
