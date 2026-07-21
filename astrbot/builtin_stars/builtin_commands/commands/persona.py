from typing import TYPE_CHECKING

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult

if TYPE_CHECKING:
    from astrbot.core.db.po import Persona


class PersonaCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    def _build_tree_output(
        self,
        folder_tree: list[dict],
        all_personas: list[Persona],
        depth: int = 0,
    ) -> list[str]:
        lines: list[str] = []
        prefix = "│ " * depth

        for folder in folder_tree:
            lines.append(f"{prefix}├ 📁 {folder['name']}/")
            folder_personas = [
                persona
                for persona in all_personas
                if persona.folder_id == folder["folder_id"]
            ]
            child_prefix = "│ " * (depth + 1)
            for persona in folder_personas:
                lines.append(f"{child_prefix}├ 👤 {persona.persona_id}")

            children = folder.get("children", [])
            if children:
                lines.extend(self._build_tree_output(children, all_personas, depth + 1))

        return lines

    async def status(self, message: AstrMessageEvent) -> None:
        umo = message.unified_msg_origin
        current_persona = "none"
        conversation_title = "none"

        conversation_id = (
            await self.context.conversation_manager.get_curr_conversation_id(umo)
        )
        default_persona = (
            await self.context.persona_manager.get_default_runtime_persona(umo=umo)
        )

        if conversation_id:
            conversation = await self.context.conversation_manager.get_conversation(
                unified_msg_origin=umo,
                conversation_id=conversation_id,
                create_if_not_exists=True,
            )
            if conversation is None:
                message.set_result(
                    MessageEventResult().message(
                        "Current conversation does not exist. Use /conversation create first."
                    )
                )
                return

            provider_settings = self.context.get_config(umo=umo).get(
                "provider_settings", {}
            )
            (
                selected_persona_id,
                _,
                force_applied_persona_id,
                _,
            ) = await self.context.persona_manager.resolve_selected_persona(
                umo=umo,
                conversation_persona_id=conversation.persona_id,
                platform_name=message.get_platform_name(),
                provider_settings=provider_settings,
            )
            if selected_persona_id == "[%None]":
                current_persona = "none"
            elif selected_persona_id:
                current_persona = selected_persona_id
            if force_applied_persona_id:
                current_persona += " (session rule)"

            conversation_title = conversation.title or "new conversation"
            conversation_title += f" ({conversation_id[:4]})"

        message.set_result(
            MessageEventResult()
            .message(
                "\n".join(
                    [
                        "[Persona]",
                        "",
                        f"Default persona: {default_persona['name']}",
                        f"Current conversation {conversation_title} persona: {current_persona}",
                        "",
                        "Create or edit personas in WebUI -> Persona.",
                    ]
                )
            )
            .use_t2i(False)
        )

    async def list_personas(self, message: AstrMessageEvent) -> None:
        folder_tree = await self.context.persona_manager.get_folder_tree()
        all_personas = self.context.persona_manager.personas

        lines = ["📂 Personas:\n"]
        tree_lines = self._build_tree_output(folder_tree, all_personas)
        lines.extend(tree_lines)

        root_personas = [
            persona for persona in all_personas if persona.folder_id is None
        ]
        if root_personas:
            if tree_lines:
                lines.append("")
            for persona in root_personas:
                lines.append(f"👤 {persona.persona_id}")

        lines.append(f"\nTotal: {len(all_personas)}")
        lines.append("\n*Use `/persona set <persona_id>` to set a persona")
        lines.append("*Use `/persona show <persona_id>` to inspect details")
        message.set_result(
            MessageEventResult().message("\n".join(lines)).use_t2i(False)
        )

    async def show(self, message: AstrMessageEvent, persona_id: str) -> None:
        persona = self.context.persona_manager.get_runtime_persona_by_id(
            persona_id.strip()
        )
        if persona is None:
            message.set_result(
                MessageEventResult().message(f"Persona `{persona_id}` does not exist.")
            )
            return

        prompt = persona["prompt"] or "(empty prompt)"
        message.set_result(
            MessageEventResult().message(f"Persona `{persona_id}`:\n{prompt}")
        )

    async def unset(self, message: AstrMessageEvent) -> None:
        umo = message.unified_msg_origin
        conversation_id = (
            await self.context.conversation_manager.get_curr_conversation_id(umo)
        )
        if not conversation_id:
            message.set_result(
                MessageEventResult().message(
                    "There is no active conversation to unset a persona from."
                )
            )
            return

        await self.context.conversation_manager.update_conversation(
            unified_msg_origin=umo,
            persona_id="[%None]",
        )
        message.set_result(
            MessageEventResult().message(
                "✅ Persona unset for the current conversation."
            )
        )

    async def set_persona(self, message: AstrMessageEvent, persona_id: str) -> None:
        persona_id = persona_id.strip()
        umo = message.unified_msg_origin
        conversation_id = (
            await self.context.conversation_manager.get_curr_conversation_id(umo)
        )
        if not conversation_id:
            message.set_result(
                MessageEventResult().message(
                    "There is no active conversation. Use /conversation create first."
                )
            )
            return

        persona = self.context.persona_manager.get_runtime_persona_by_id(persona_id)
        if persona is None:
            message.set_result(
                MessageEventResult().message(
                    "Persona does not exist. Use /persona list to inspect available personas."
                )
            )
            return

        conversation = await self.context.conversation_manager.get_conversation(
            unified_msg_origin=umo,
            conversation_id=conversation_id,
            create_if_not_exists=True,
        )
        if conversation is None:
            message.set_result(
                MessageEventResult().message(
                    "Current conversation does not exist. Use /conversation create first."
                )
            )
            return

        provider_settings = self.context.get_config(umo=umo).get(
            "provider_settings", {}
        )
        (
            _,
            _,
            force_applied_persona_id,
            _,
        ) = await self.context.persona_manager.resolve_selected_persona(
            umo=umo,
            conversation_persona_id=conversation.persona_id,
            platform_name=message.get_platform_name(),
            provider_settings=provider_settings,
        )

        await self.context.conversation_manager.update_conversation(
            unified_msg_origin=umo,
            persona_id=persona_id,
        )
        force_warning = ""
        if force_applied_persona_id:
            force_warning = (
                " A session rule is forcing another persona, so this selection "
                "will not take effect yet."
            )
        message.set_result(
            MessageEventResult().message(
                "✅ Persona updated. Use /conversation reset if you need a clean context after "
                "switching personas." + force_warning
            )
        )
