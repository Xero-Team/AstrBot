from astrbot.core.prompt_mgr import PromptManager
from astrbot.core.sentinels import NOT_GIVEN


class PromptServiceError(Exception):
    pass


class PromptService:
    def __init__(self, prompt_manager: PromptManager) -> None:
        self.prompt_mgr = prompt_manager

    async def list_prompts(
        self,
        folder_id: str | None,
        filter_by_folder: bool,
    ) -> list[dict]:
        if filter_by_folder:
            prompts = await self.prompt_mgr.get_prompts_by_folder(
                folder_id if folder_id else None
            )
        else:
            prompts = await self.prompt_mgr.get_all_prompts()
        return [self.serialize_prompt(prompt) for prompt in prompts]

    async def get_prompt_detail(self, data: object) -> dict:
        payload = self._payload(data)
        prompt_id = payload.get("prompt_id")

        if not prompt_id:
            raise PromptServiceError("缺少必要参数: prompt_id")

        prompt = await self.prompt_mgr.get_prompt(prompt_id)
        if not prompt:
            raise PromptServiceError("提示词不存在")

        return self.serialize_prompt(prompt)

    async def create_prompt(self, data: object) -> dict:
        payload = self._payload(data)
        raw_prompt_id = payload.get("prompt_id")
        raw_system_prompt = payload.get("system_prompt")
        prompt_id = str(raw_prompt_id).strip() if raw_prompt_id is not None else ""
        system_prompt = (
            str(raw_system_prompt).strip() if raw_system_prompt is not None else ""
        )
        begin_dialogs = payload.get("begin_dialogs", [])
        tools = payload.get("tools")
        skills = payload.get("skills")
        custom_error_message = self._normalize_custom_error_message(
            payload.get("custom_error_message")
        )
        folder_id = payload.get("folder_id")
        sort_order = payload.get("sort_order", 0)

        if not prompt_id:
            raise PromptServiceError("提示词ID不能为空")
        if not system_prompt:
            raise PromptServiceError("系统提示词不能为空")

        self._validate_begin_dialogs(begin_dialogs)

        prompt = await self.prompt_mgr.create_prompt(
            prompt_id=prompt_id,
            system_prompt=system_prompt,
            begin_dialogs=begin_dialogs if begin_dialogs else None,
            tools=tools if tools is not None else None,
            skills=skills if skills is not None else None,
            custom_error_message=custom_error_message,
            folder_id=folder_id,
            sort_order=sort_order,
        )

        return {
            "message": "提示词创建成功",
            "prompt": self.serialize_prompt(prompt, empty_lists_for_tools=True),
        }

    async def update_prompt(self, data: object) -> dict:
        payload = self._payload(data)
        prompt_id = payload.get("prompt_id")
        system_prompt = payload.get("system_prompt")
        begin_dialogs = payload.get("begin_dialogs")
        has_tools = "tools" in payload
        tools = payload.get("tools")
        has_skills = "skills" in payload
        skills = payload.get("skills")
        has_custom_error_message = "custom_error_message" in payload
        custom_error_message = payload.get("custom_error_message")

        if not prompt_id:
            raise PromptServiceError("缺少必要参数: prompt_id")

        if has_custom_error_message:
            custom_error_message = self._normalize_custom_error_message(
                custom_error_message
            )

        if begin_dialogs is not None:
            self._validate_begin_dialogs(begin_dialogs)

        update_kwargs = {
            "prompt_id": prompt_id,
            "system_prompt": system_prompt,
            "begin_dialogs": begin_dialogs,
        }
        if has_tools:
            update_kwargs["tools"] = tools
        if has_skills:
            update_kwargs["skills"] = skills
        if has_custom_error_message:
            update_kwargs["custom_error_message"] = custom_error_message

        await self.prompt_mgr.update_prompt(**update_kwargs)
        return {"message": "提示词更新成功"}

    async def delete_prompt(self, data: object) -> dict:
        payload = self._payload(data)
        prompt_id = payload.get("prompt_id")

        if not prompt_id:
            raise PromptServiceError("缺少必要参数: prompt_id")

        await self.prompt_mgr.delete_prompt(prompt_id)
        return {"message": "提示词删除成功"}

    async def move_prompt(self, data: object) -> dict:
        payload = self._payload(data)
        prompt_id = payload.get("prompt_id")
        folder_id = payload.get("folder_id")

        if not prompt_id:
            raise PromptServiceError("缺少必要参数: prompt_id")

        await self.prompt_mgr.move_prompt_to_folder(prompt_id, folder_id)
        return {"message": "提示词移动成功"}

    async def list_folders(self, parent_id: str | None) -> list[dict]:
        if parent_id == "":
            parent_id = None
        folders = await self.prompt_mgr.get_folders(parent_id)
        return [self.serialize_folder(folder) for folder in folders]

    async def get_folder_tree(self):
        return await self.prompt_mgr.get_folder_tree()

    async def get_folder_detail(self, data: object) -> dict:
        payload = self._payload(data)
        folder_id = payload.get("folder_id")

        if not folder_id:
            raise PromptServiceError("缺少必要参数: folder_id")

        folder = await self.prompt_mgr.get_folder(folder_id)
        if not folder:
            raise PromptServiceError("文件夹不存在")

        return self.serialize_folder(folder)

    async def create_folder(self, data: object) -> dict:
        payload = self._payload(data)
        name = str(payload.get("name", "")).strip()
        parent_id = payload.get("parent_id")
        description = payload.get("description")
        sort_order = payload.get("sort_order", 0)

        if not name:
            raise PromptServiceError("文件夹名称不能为空")

        folder = await self.prompt_mgr.create_folder(
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

        return {
            "message": "文件夹创建成功",
            "folder": self.serialize_folder(folder),
        }

    async def update_folder(self, data: object) -> dict:
        payload = self._payload(data)
        folder_id = payload.get("folder_id")
        name = payload.get("name")
        parent_id = payload.get("parent_id") if "parent_id" in payload else NOT_GIVEN
        description = (
            payload.get("description") if "description" in payload else NOT_GIVEN
        )
        sort_order = payload.get("sort_order")

        if not folder_id:
            raise PromptServiceError("缺少必要参数: folder_id")

        await self.prompt_mgr.update_folder(
            folder_id=folder_id,
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )

        return {"message": "文件夹更新成功"}

    async def delete_folder(self, data: object) -> dict:
        payload = self._payload(data)
        folder_id = payload.get("folder_id")

        if not folder_id:
            raise PromptServiceError("缺少必要参数: folder_id")

        await self.prompt_mgr.delete_folder(folder_id)
        return {"message": "文件夹删除成功"}

    async def reorder_items(self, data: object) -> dict:
        payload = self._payload(data)
        items = payload.get("items", [])

        if not items:
            raise PromptServiceError("items 不能为空")

        for item in items:
            if not all(key in item for key in ("id", "type", "sort_order")):
                raise PromptServiceError("每个 item 必须包含 id, type, sort_order 字段")
            if item["type"] not in ("prompt", "folder"):
                raise PromptServiceError("type 字段必须是 'prompt' 或 'folder'")

        await self.prompt_mgr.batch_update_sort_order(items)
        return {"message": "排序更新成功"}

    @staticmethod
    def serialize_prompt(prompt, empty_lists_for_tools: bool = False) -> dict:
        return {
            "prompt_id": prompt.prompt_id,
            "system_prompt": prompt.system_prompt,
            "begin_dialogs": prompt.begin_dialogs or [],
            "tools": (prompt.tools or []) if empty_lists_for_tools else prompt.tools,
            "skills": (prompt.skills or []) if empty_lists_for_tools else prompt.skills,
            "custom_error_message": prompt.custom_error_message,
            "folder_id": prompt.folder_id,
            "sort_order": prompt.sort_order,
            "created_at": prompt.created_at.isoformat() if prompt.created_at else None,
            "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
        }

    @staticmethod
    def serialize_folder(folder) -> dict:
        return {
            "folder_id": folder.folder_id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "description": folder.description,
            "sort_order": folder.sort_order,
            "created_at": folder.created_at.isoformat() if folder.created_at else None,
            "updated_at": folder.updated_at.isoformat() if folder.updated_at else None,
        }

    @staticmethod
    def _normalize_custom_error_message(value):
        if value is not None:
            if not isinstance(value, str):
                raise PromptServiceError("自定义报错回复信息必须是字符串")
            return value.strip() or None
        return None

    @staticmethod
    def _validate_begin_dialogs(begin_dialogs) -> None:
        if begin_dialogs and len(begin_dialogs) % 2 != 0:
            raise PromptServiceError("预设对话数量必须为偶数（用户和助手轮流对话）")

    @staticmethod
    def _payload(data: object) -> dict:
        return data if isinstance(data, dict) else {}
