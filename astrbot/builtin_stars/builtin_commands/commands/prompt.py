from collections.abc import Sequence
from typing import TYPE_CHECKING

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n

if TYPE_CHECKING:
    from astrbot.core.db.po import Prompt


class PromptCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    def _build_tree_output(
        self,
        folder_tree: list[dict],
        all_prompts: Sequence[Prompt],
        depth: int = 0,
    ) -> list[str]:
        lines: list[str] = []
        prefix = "| " * depth

        for folder in folder_tree:
            lines.append(f"{prefix}+ {folder['name']}/")
            folder_prompts = [
                prompt
                for prompt in all_prompts
                if prompt.folder_id == folder["folder_id"]
            ]
            child_prefix = "| " * (depth + 1)
            for prompt in folder_prompts:
                lines.append(f"{child_prefix}- {prompt.prompt_id}")

            children = folder.get("children", [])
            if children:
                lines.extend(self._build_tree_output(children, all_prompts, depth + 1))

        return lines

    async def status(self, message: AstrMessageEvent) -> None:
        umo = message.unified_msg_origin
        none_label = await self.context.i18n.t(message, "prompt.status.none")
        current_prompt = none_label
        conversation_title = none_label

        conversation_id = await self.context.conversations.current_id(umo)
        default_prompt = await self.context.prompts.default(umo=umo)

        if conversation_id:
            conversation = await self.context.conversations.get(
                umo,
                conversation_id,
                create_if_missing=True,
            )
            if conversation is None:
                await reply_i18n(self.context, message, "prompt.status.no_conversation")
                return

            (
                selected_prompt_id,
                _,
                force_applied_prompt_id,
                _,
            ) = await self.context.prompts.resolve(
                umo=umo,
                conversation_prompt_id=conversation.prompt_id,
                platform_name=message.get_platform_name(),
            )
            if selected_prompt_id == "[%None]":
                current_prompt = none_label
            elif selected_prompt_id:
                current_prompt = selected_prompt_id
            if force_applied_prompt_id:
                current_prompt += " " + await self.context.i18n.t(
                    message, "prompt.status.session_rule"
                )

            new_title = await self.context.i18n.t(message, "prompt.status.new")
            conversation_title = conversation.title or new_title
            conversation_title += f" ({conversation_id[:4]})"

        await reply_i18n(
            self.context,
            message,
            "prompt.status.body",
            default_prompt=default_prompt["name"],
            conversation_title=conversation_title,
            current_prompt=current_prompt,
        )

    async def list_prompts(self, message: AstrMessageEvent) -> None:
        folder_tree = await self.context.prompts.folders()
        all_prompts = self.context.prompts.all()
        tree_lines = self._build_tree_output(folder_tree, all_prompts)
        root_prompts = [prompt for prompt in all_prompts if prompt.folder_id is None]
        extra_lines: list[str] = []
        if root_prompts:
            if tree_lines:
                extra_lines.append("")
            for prompt in root_prompts:
                extra_lines.append(f"- {prompt.prompt_id}")
        listing = "\n".join([*tree_lines, *extra_lines])
        await reply_i18n(
            self.context,
            message,
            "prompt.list.body",
            listing=listing,
            total=len(all_prompts),
        )

    async def show(self, message: AstrMessageEvent, prompt_id: str) -> None:
        prompt = self.context.prompts.get(prompt_id.strip())
        if prompt is None:
            await reply_i18n(
                self.context,
                message,
                "prompt.show.missing",
                prompt_id=prompt_id,
            )
            return
        prompt = prompt["prompt"] or await self.context.i18n.t(
            message, "prompt.show.empty_prompt"
        )
        await reply_i18n(
            self.context,
            message,
            "prompt.show.body",
            prompt_id=prompt_id,
            prompt=prompt,
        )

    async def unset(self, message: AstrMessageEvent) -> None:
        umo = message.unified_msg_origin
        conversation_id = await self.context.conversations.current_id(umo)
        if not conversation_id:
            await reply_i18n(self.context, message, "prompt.unset.none")
            return
        await self.context.conversations.update(
            umo,
            prompt_id="[%None]",
        )
        await reply_i18n(self.context, message, "prompt.unset.ok")

    async def set_prompt(self, message: AstrMessageEvent, prompt_id: str) -> None:
        prompt_id = prompt_id.strip()
        umo = message.unified_msg_origin
        conversation_id = await self.context.conversations.current_id(umo)
        if not conversation_id:
            await reply_i18n(self.context, message, "prompt.set.none")
            return

        prompt = self.context.prompts.get(prompt_id)
        if prompt is None:
            await reply_i18n(self.context, message, "prompt.set.missing")
            return

        conversation = await self.context.conversations.get(
            umo,
            conversation_id,
            create_if_missing=True,
        )
        if conversation is None:
            await reply_i18n(self.context, message, "prompt.set.no_conversation")
            return

        (
            _,
            _,
            force_applied_prompt_id,
            _,
        ) = await self.context.prompts.resolve(
            umo=umo,
            conversation_prompt_id=conversation.prompt_id,
            platform_name=message.get_platform_name(),
        )
        await self.context.conversations.update(
            umo,
            prompt_id=prompt_id,
        )
        force_warning = ""
        if force_applied_prompt_id:
            force_warning = await self.context.i18n.t(
                message, "prompt.set.force_warning"
            )
        await reply_i18n(
            self.context,
            message,
            "prompt.set.ok",
            force_warning=force_warning,
        )
