import typing as T

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select, update

from astrbot.core.db.po import Prompt, PromptFolder
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session
from astrbot.core.sentinels import NOT_GIVEN


class PromptStoreMixin(DatabaseStoreMixin):
    async def insert_prompt(
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
        """Insert a new prompt record."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                new_prompt = Prompt(
                    prompt_id=prompt_id,
                    system_prompt=system_prompt,
                    begin_dialogs=begin_dialogs or [],
                    tools=tools,
                    skills=skills,
                    custom_error_message=custom_error_message,
                    folder_id=folder_id,
                    sort_order=sort_order,
                )
                session.add(new_prompt)
                await session.flush()
                await session.refresh(new_prompt)
                return new_prompt

    async def get_prompt_by_id(self, prompt_id: str) -> Prompt | None:
        """Get a prompt by its ID."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(Prompt).where(Prompt.prompt_id == prompt_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_prompts(self) -> list[Prompt]:
        """Get all prompts for a specific bot."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(Prompt)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_prompt(
        self,
        prompt_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None | object = NOT_GIVEN,
        skills: list[str] | None | object = NOT_GIVEN,
        custom_error_message: str | None | object = NOT_GIVEN,
    ) -> Prompt | None:
        """Update a prompt's system prompt or begin dialogs."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                query = update(Prompt).where(col(Prompt.prompt_id) == prompt_id)
                values = {}
                if system_prompt is not None:
                    values["system_prompt"] = system_prompt
                if begin_dialogs is not None:
                    values["begin_dialogs"] = begin_dialogs
                if tools is not NOT_GIVEN:
                    values["tools"] = tools
                if skills is not NOT_GIVEN:
                    values["skills"] = skills
                if custom_error_message is not NOT_GIVEN:
                    values["custom_error_message"] = custom_error_message
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_prompt_by_id(prompt_id)

    async def delete_prompt(self, prompt_id) -> None:
        """Delete a prompt by its ID."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Prompt).where(col(Prompt.prompt_id) == prompt_id),
                )

    # ====
    # Prompt Folder Management
    # ====

    async def insert_prompt_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PromptFolder:
        """Insert a new prompt folder."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                new_folder = PromptFolder(
                    name=name,
                    parent_id=parent_id,
                    description=description,
                    sort_order=sort_order,
                )
                session.add(new_folder)
                await session.flush()
                await session.refresh(new_folder)
                return new_folder

    async def get_prompt_folder_by_id(self, folder_id: str) -> PromptFolder | None:
        """Get a prompt folder by its folder_id."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(PromptFolder).where(PromptFolder.folder_id == folder_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_prompt_folders(
        self, parent_id: str | None = None
    ) -> list[PromptFolder]:
        """Get all prompt folders, optionally filtered by parent_id.

        Args:
            parent_id: If None, returns root folders only. If specified, returns
                       children of that folder.
        """
        async with store_session(self) as session:
            session: AsyncSession
            if parent_id is None:
                # Get root folders (parent_id is NULL)
                query = (
                    select(PromptFolder)
                    .where(col(PromptFolder.parent_id).is_(None))
                    .order_by(col(PromptFolder.sort_order), col(PromptFolder.name))
                )
            else:
                query = (
                    select(PromptFolder)
                    .where(PromptFolder.parent_id == parent_id)
                    .order_by(col(PromptFolder.sort_order), col(PromptFolder.name))
                )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def get_all_prompt_folders(self) -> list[PromptFolder]:
        """Get all prompt folders."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(PromptFolder).order_by(
                col(PromptFolder.sort_order), col(PromptFolder.name)
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_prompt_folder(
        self,
        folder_id: str,
        name: str | None = None,
        parent_id: T.Any = NOT_GIVEN,
        description: T.Any = NOT_GIVEN,
        sort_order: int | None = None,
    ) -> PromptFolder | None:
        """Update a prompt folder."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                query = update(PromptFolder).where(
                    col(PromptFolder.folder_id) == folder_id
                )
                values: dict[str, T.Any] = {}
                if name is not None:
                    values["name"] = name
                if parent_id is not NOT_GIVEN:
                    values["parent_id"] = parent_id
                if description is not NOT_GIVEN:
                    values["description"] = description
                if sort_order is not None:
                    values["sort_order"] = sort_order
                if not values:
                    return None
                query = query.values(**values)
                await session.execute(query)
        return await self.get_prompt_folder_by_id(folder_id)

    async def delete_prompt_folder(self, folder_id: str) -> None:
        """Delete a prompt folder by its folder_id.

        Note: This will also set folder_id to NULL for all prompts in this folder,
        moving them to the root directory.
        """
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                # Move prompts to root directory
                await session.execute(
                    update(Prompt)
                    .where(col(Prompt.folder_id) == folder_id)
                    .values(folder_id=None)
                )
                # Delete the folder
                await session.execute(
                    delete(PromptFolder).where(
                        col(PromptFolder.folder_id) == folder_id
                    ),
                )

    async def move_prompt_to_folder(
        self, prompt_id: str, folder_id: str | None
    ) -> Prompt | None:
        """Move a prompt to a folder (or root if folder_id is None)."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(Prompt)
                    .where(col(Prompt.prompt_id) == prompt_id)
                    .values(folder_id=folder_id)
                )
        return await self.get_prompt_by_id(prompt_id)

    async def get_prompts_by_folder(self, folder_id: str | None = None) -> list[Prompt]:
        """Get all prompts in a specific folder.

        Args:
            folder_id: If None, returns prompts in root directory.
        """
        async with store_session(self) as session:
            session: AsyncSession
            if folder_id is None:
                query = (
                    select(Prompt)
                    .where(col(Prompt.folder_id).is_(None))
                    .order_by(col(Prompt.sort_order), col(Prompt.prompt_id))
                )
            else:
                query = (
                    select(Prompt)
                    .where(Prompt.folder_id == folder_id)
                    .order_by(col(Prompt.sort_order), col(Prompt.prompt_id))
                )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def batch_update_sort_order(
        self,
        items: list[dict],
    ) -> None:
        """Batch update sort_order for prompts and/or folders.

        Args:
            items: List of dicts with keys:
                - id: The prompt_id or folder_id
                - type: Either "prompt" or "folder"
                - sort_order: The new sort_order value
        """
        if not items:
            return

        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                for item in items:
                    item_id = item.get("id")
                    item_type = item.get("type")
                    sort_order = item.get("sort_order")

                    if item_id is None or item_type is None or sort_order is None:
                        continue

                    if item_type == "prompt":
                        await session.execute(
                            update(Prompt)
                            .where(col(Prompt.prompt_id) == item_id)
                            .values(sort_order=sort_order)
                        )
                    elif item_type == "folder":
                        await session.execute(
                            update(PromptFolder)
                            .where(col(PromptFolder.folder_id) == item_id)
                            .values(sort_order=sort_order)
                        )
