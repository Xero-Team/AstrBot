from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.agent_runner import get_prompt_id
from astrbot.core.db.po import Prompt, PromptFolder
from astrbot.core.db.protocols import PromptStore
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.prompt_models import PromptSpec
from astrbot.core.sentinels import NOT_GIVEN
from astrbot.core.utils.shared_preferences import SharedPreferences

DEFAULT_PROMPT_SPEC = PromptSpec(
    prompt="You are a helpful and friendly assistant.",
    name="default",
    begin_dialogs=[],
    tools=None,
    skills=None,
    custom_error_message=None,
    _begin_dialogs_processed=[],
)


class PromptManager:
    def __init__(
        self,
        db_helper: PromptStore,
        acm: AstrBotConfigManager,
        preferences: SharedPreferences,
    ) -> None:
        self.db = db_helper
        self.acm = acm
        self.preferences = preferences
        self.default_prompt: str = get_prompt_id(
            acm.default_conf.get("agent_runner", {})
        )
        self.prompts: list[Prompt] = []
        self.runtime_prompts: list[PromptSpec] = []
        self.selected_runtime_prompt: PromptSpec | None = None

    async def initialize(self) -> None:
        self.prompts = await self.get_all_prompts()
        self._refresh_runtime_prompts()
        logger.info("Loaded %s prompts.", len(self.prompts))

    async def get_prompt(self, prompt_id: str):
        """获取指定 prompt 的信息"""
        prompt = await self.db.get_prompt_by_id(prompt_id)
        if not prompt:
            raise ValueError(f"Prompt with ID {prompt_id} does not exist.")
        return prompt

    def get_runtime_prompt_by_id(self, prompt_id: str | None) -> PromptSpec | None:
        """Resolve a runtime prompt object by id.

        - None/empty id returns None.
        - "default" maps to in-memory DEFAULT_PROMPT_SPEC.
        - Otherwise search in runtime_prompts by prompt name.
        """
        if not prompt_id:
            return None
        if prompt_id == "default":
            return DEFAULT_PROMPT_SPEC
        return next(
            (prompt for prompt in self.runtime_prompts if prompt["name"] == prompt_id),
            None,
        )

    async def get_default_runtime_prompt(
        self,
        umo: str | MessageSession | None = None,
    ) -> PromptSpec:
        """获取默认 prompt"""
        cfg = self.acm.get_conf(umo)
        default_prompt_id = get_prompt_id(cfg.get("agent_runner", {}))
        return self.get_runtime_prompt_by_id(default_prompt_id) or DEFAULT_PROMPT_SPEC

    async def resolve_selected_prompt(
        self,
        *,
        umo: str | MessageSession,
        conversation_prompt_id: str | None,
        platform_name: str,
    ) -> tuple[str | None, PromptSpec | None, str | None, bool]:
        """解析当前会话最终生效的提示词。

        Returns:
            tuple:
                - selected prompt_id
                - selected prompt object
                - force applied prompt_id from session rule
                - whether use webchat special default prompt
        """
        session_service_config = (
            await self.preferences.get_async(
                scope="umo",
                scope_id=str(umo),
                key="session_service_config",
                default={},
            )
            or {}
        )

        force_applied_prompt_id = session_service_config.get("prompt_id")
        prompt_id = force_applied_prompt_id

        if not prompt_id:
            prompt_id = conversation_prompt_id
            if prompt_id == "[%None]":
                pass
            elif prompt_id is None:
                cfg = self.acm.get_conf(umo)
                prompt_id = get_prompt_id(cfg.get("agent_runner", {}))

        prompt = next(
            (item for item in self.runtime_prompts if item["name"] == prompt_id),
            None,
        )

        use_webchat_special_default = False
        if not prompt and platform_name == "webchat" and prompt_id != "[%None]":
            prompt_id = "_chatui_default_"
            use_webchat_special_default = True

        return (
            prompt_id,
            prompt,
            force_applied_prompt_id,
            use_webchat_special_default,
        )

    async def delete_prompt(self, prompt_id: str) -> None:
        """删除指定 prompt"""
        if not await self.db.get_prompt_by_id(prompt_id):
            raise ValueError(f"Prompt with ID {prompt_id} does not exist.")
        await self.db.delete_prompt(prompt_id)
        self.prompts = [p for p in self.prompts if p.prompt_id != prompt_id]
        self._refresh_runtime_prompts()

    async def update_prompt(
        self,
        prompt_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None | object = NOT_GIVEN,
        skills: list[str] | None | object = NOT_GIVEN,
        custom_error_message: str | None | object = NOT_GIVEN,
    ):
        """更新指定 prompt 的信息。tools 参数为 None 时表示使用所有工具，空列表表示不使用任何工具"""
        existing_prompt = await self.db.get_prompt_by_id(prompt_id)
        if not existing_prompt:
            raise ValueError(f"Prompt with ID {prompt_id} does not exist.")
        update_kwargs = {}
        if tools is not NOT_GIVEN:
            update_kwargs["tools"] = tools
        if skills is not NOT_GIVEN:
            update_kwargs["skills"] = skills
        if custom_error_message is not NOT_GIVEN:
            update_kwargs["custom_error_message"] = custom_error_message

        prompt = await self.db.update_prompt(
            prompt_id,
            system_prompt,
            begin_dialogs,
            **update_kwargs,
        )
        if prompt:
            for i, p in enumerate(self.prompts):
                if p.prompt_id == prompt_id:
                    self.prompts[i] = prompt
                    break
        self._refresh_runtime_prompts()
        return prompt

    async def get_all_prompts(self) -> list[Prompt]:
        """获取所有 prompts"""
        return await self.db.get_prompts()

    async def get_prompts_by_folder(self, folder_id: str | None = None) -> list[Prompt]:
        """获取指定文件夹中的 prompts

        Args:
            folder_id: 文件夹 ID，None 表示根目录
        """
        return await self.db.get_prompts_by_folder(folder_id)

    async def move_prompt_to_folder(
        self, prompt_id: str, folder_id: str | None
    ) -> Prompt | None:
        """移动 prompt 到指定文件夹

        Args:
            prompt_id: Prompt ID
            folder_id: 目标文件夹 ID，None 表示移动到根目录
        """
        prompt = await self.db.move_prompt_to_folder(prompt_id, folder_id)
        if prompt:
            for i, p in enumerate(self.prompts):
                if p.prompt_id == prompt_id:
                    self.prompts[i] = prompt
                    break
        return prompt

    # ====
    # Prompt Folder Management
    # ====

    async def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PromptFolder:
        """创建新的文件夹"""
        return await self.db.insert_prompt_folder(
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def get_folder(self, folder_id: str) -> PromptFolder | None:
        """获取指定文件夹"""
        return await self.db.get_prompt_folder_by_id(folder_id)

    async def get_folders(self, parent_id: str | None = None) -> list[PromptFolder]:
        """获取文件夹列表

        Args:
            parent_id: 父文件夹 ID，None 表示获取根目录下的文件夹
        """
        return await self.db.get_prompt_folders(parent_id)

    async def get_all_folders(self) -> list[PromptFolder]:
        """获取所有文件夹"""
        return await self.db.get_all_prompt_folders()

    async def update_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: str | None | object = NOT_GIVEN,
        description: str | None | object = NOT_GIVEN,
        sort_order: int | None = None,
    ) -> PromptFolder | None:
        """更新文件夹信息"""
        return await self.db.update_prompt_folder(
            folder_id=folder_id,
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

    async def delete_folder(self, folder_id: str) -> None:
        """删除文件夹

        Note: 文件夹内的 prompts 会被移动到根目录
        """
        await self.db.delete_prompt_folder(folder_id)

    async def batch_update_sort_order(self, items: list[dict]) -> None:
        """批量更新 prompts 和/或 folders 的排序顺序

        Args:
            items: 包含以下键的字典列表：
                - id: prompt_id 或 folder_id
                - type: "prompt" 或 "folder"
                - sort_order: 新的排序顺序值
        """
        await self.db.batch_update_sort_order(items)
        # 刷新缓存
        self.prompts = await self.get_all_prompts()
        self._refresh_runtime_prompts()

    async def get_folder_tree(self) -> list[dict]:
        """获取文件夹树形结构

        Returns:
            树形结构的文件夹列表，每个文件夹包含 children 子列表
        """
        all_folders = await self.get_all_folders()
        folder_map: dict[str, dict] = {}

        # 创建文件夹字典
        for folder in all_folders:
            folder_map[folder.folder_id] = {
                "folder_id": folder.folder_id,
                "name": folder.name,
                "parent_id": folder.parent_id,
                "description": folder.description,
                "sort_order": folder.sort_order,
                "children": [],
            }

        # 构建树形结构
        root_folders = []
        for folder_id, folder_data in folder_map.items():
            parent_id = folder_data["parent_id"]
            if parent_id is None:
                root_folders.append(folder_data)
            elif parent_id in folder_map:
                folder_map[parent_id]["children"].append(folder_data)

        # 递归排序
        def sort_folders(folders: list[dict]) -> list[dict]:
            folders.sort(key=lambda f: (f["sort_order"], f["name"]))
            for folder in folders:
                if folder["children"]:
                    folder["children"] = sort_folders(folder["children"])
            return folders

        return sort_folders(root_folders)

    async def create_prompt(
        self,
        prompt_id: str,
        system_prompt: str,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int = 0,
    ) -> Prompt:
        """创建新的 prompt。

        Args:
            prompt_id: Prompt 唯一标识
            system_prompt: 系统提示词
            begin_dialogs: 预设对话列表
            tools: 工具列表，None 表示使用所有工具，空列表表示不使用任何工具
            skills: Skills 列表，None 表示使用所有 Skills，空列表表示不使用任何 Skills
            folder_id: 所属文件夹 ID，None 表示根目录
            sort_order: 排序顺序
        """
        if await self.db.get_prompt_by_id(prompt_id):
            raise ValueError(f"Prompt with ID {prompt_id} already exists.")
        new_prompt = await self.db.insert_prompt(
            prompt_id,
            system_prompt,
            begin_dialogs,
            tools=tools,
            skills=skills,
            custom_error_message=custom_error_message,
            folder_id=folder_id,
            sort_order=sort_order,
        )
        self.prompts.append(new_prompt)
        self._refresh_runtime_prompts()
        return new_prompt

    def _refresh_runtime_prompts(self) -> None:
        runtime_prompts: list[PromptSpec] = []
        selected_runtime_prompt: PromptSpec | None = None

        for prompt in self.prompts:
            begin_dialogs = prompt.begin_dialogs or []
            bd_processed = []
            if begin_dialogs:
                if len(begin_dialogs) % 2 != 0:
                    logger.error(
                        f"{prompt.prompt_id} 提示词情景预设对话格式不对，条数应该为偶数。",
                    )
                    begin_dialogs = []
                user_turn = True
                for dialog in begin_dialogs:
                    bd_processed.append(
                        {
                            "role": "user" if user_turn else "assistant",
                            "content": dialog,
                            "_no_save": True,  # 不持久化到 db
                        },
                    )
                    user_turn = not user_turn

            try:
                runtime_prompt = PromptSpec(
                    prompt=prompt.system_prompt,
                    name=prompt.prompt_id,
                    begin_dialogs=begin_dialogs,
                    tools=prompt.tools,
                    skills=prompt.skills,
                    custom_error_message=prompt.custom_error_message,
                    _begin_dialogs_processed=bd_processed,
                )
                if runtime_prompt["name"] == self.default_prompt:
                    selected_runtime_prompt = runtime_prompt
                runtime_prompts.append(runtime_prompt)
            except Exception as e:
                logger.error(f"解析 Prompt 配置失败：{e}")

        if not selected_runtime_prompt and runtime_prompts:
            selected_runtime_prompt = runtime_prompts[0]

        if not selected_runtime_prompt:
            selected_runtime_prompt = DEFAULT_PROMPT_SPEC
            runtime_prompts.append(selected_runtime_prompt)

        self.runtime_prompts = runtime_prompts
        self.selected_runtime_prompt = selected_runtime_prompt
