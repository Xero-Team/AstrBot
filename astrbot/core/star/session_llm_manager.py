"""会话服务管理器 - 负责管理每个会话的LLM、TTS等服务的启停状态"""

from astrbot import logger
from astrbot.core.auth.admission import (
    SESSION_SERVICE_CONFIG_KEY,
    composed_llm_enabled,
    is_webchat_event,
    overlay_flag_enabled,
    sender_admission_key_from_event,
    sender_overlay_from_config,
    session_admission_key_from_event,
    session_admission_key_from_umo,
    session_overlay_from_config,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.shared_preferences import SharedPreferences


def sender_service_config(existing: object, **fields: bool | None) -> dict[str, bool]:
    """Return a sender overlay with only ``blocked`` and ``llm_enabled``.

    Args:
        existing: Stored preference value, typically a dict.
        **fields: Overlay fields to write. ``None`` clears the field so it
            returns to "unwritten / follow the session".

    Returns:
        A mapping that preserves existing bool overlays and applies ``fields``.
        Extra keys such as prompt, TTS, KB, or Provider are dropped.
    """
    config: dict[str, bool] = {}
    if isinstance(existing, dict):
        blocked = existing.get("blocked")
        if isinstance(blocked, bool):
            config["blocked"] = blocked
        llm_enabled = existing.get("llm_enabled")
        if isinstance(llm_enabled, bool):
            config["llm_enabled"] = llm_enabled
    for name, value in fields.items():
        if value is None:
            config.pop(name, None)
        else:
            config[name] = value
    return config


class SessionServiceManager:
    """管理会话级别的服务启停状态，包括LLM和TTS"""

    def __init__(self, preferences: SharedPreferences) -> None:
        self.preferences = preferences

    async def _service_config(self, scope: str, scope_id: str) -> dict:
        config = await self.preferences.get_async(
            scope=scope,
            scope_id=scope_id,
            key=SESSION_SERVICE_CONFIG_KEY,
            default={},
        )
        return config if isinstance(config, dict) else {}

    def _llm_scope_id(self, session_id: str) -> str:
        return session_admission_key_from_umo(session_id) or session_id

    def _sender_scope_id(self, event_or_key: AstrMessageEvent | str) -> str:
        if isinstance(event_or_key, str):
            return event_or_key
        return sender_admission_key_from_event(event_or_key)

    async def _put_sender_overlay(self, scope_id: str, **fields: bool) -> None:
        await self.preferences.put_async(
            scope="sender",
            scope_id=scope_id,
            key=SESSION_SERVICE_CONFIG_KEY,
            value=sender_service_config(
                await self._service_config("sender", scope_id),
                **fields,
            ),
        )

    async def is_llm_enabled_for_session(self, session_id: str) -> bool:
        """检查LLM是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用

        """
        scope_id = self._llm_scope_id(session_id)
        overlay = session_overlay_from_config(
            await self._service_config("umo", scope_id)
        )
        return overlay_flag_enabled(overlay.llm_enabled, scope_id=scope_id)

    async def set_llm_status_for_session(self, session_id: str, enabled: bool) -> None:
        """设置LLM在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用

        """
        scope_id = self._llm_scope_id(session_id)
        session_config = await self._service_config("umo", scope_id)
        session_config["llm_enabled"] = enabled
        await self.preferences.put_async(
            scope="umo",
            scope_id=scope_id,
            key=SESSION_SERVICE_CONFIG_KEY,
            value=session_config,
        )

    async def should_process_llm_request(self, event: AstrMessageEvent) -> bool:
        """检查是否应该处理LLM请求

        Empty sender overlays follow the canonical session ``llm_enabled``
        switch. A written sender overlay is more specific, including VIP
        enable. Unique-session UMO rows are not read.

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过

        """
        session_overlay = session_overlay_from_config(
            await self._service_config("umo", session_admission_key_from_event(event))
        )
        sender_overlay = sender_overlay_from_config(
            await self._service_config("sender", sender_admission_key_from_event(event))
        )
        return composed_llm_enabled(
            session_overlay,
            sender_overlay,
            unwritten_enabled=is_webchat_event(event),
        )

    # =============================================================================
    # TTS 相关方法
    # =============================================================================

    async def is_tts_enabled_for_session(self, session_id: str) -> bool:
        """检查TTS是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用

        """
        tts_enabled = (await self._service_config("umo", session_id)).get("tts_enabled")
        return overlay_flag_enabled(tts_enabled, scope_id=session_id)

    async def set_tts_status_for_session(self, session_id: str, enabled: bool) -> None:
        """设置TTS在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用

        """
        session_config = await self._service_config("umo", session_id)
        session_config["tts_enabled"] = enabled
        await self.preferences.put_async(
            scope="umo",
            scope_id=session_id,
            key=SESSION_SERVICE_CONFIG_KEY,
            value=session_config,
        )

        logger.info(
            f"会话 {session_id} 的TTS状态已更新为: {'启用' if enabled else '禁用'}",
        )

    async def should_process_tts_request(self, event: AstrMessageEvent) -> bool:
        """检查是否应该处理TTS请求

        Args:
            event: 消息事件

        Returns:
            bool: True表示应该处理，False表示跳过

        """
        session_id = event.unified_msg_origin
        return await self.is_tts_enabled_for_session(session_id)

    # =============================================================================
    # 会话整体启停相关方法
    # =============================================================================

    async def is_session_enabled(self, session_id: str) -> bool:
        """检查会话是否整体启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用

        """
        overlay = session_overlay_from_config(
            await self._service_config("umo", session_id)
        )
        return overlay_flag_enabled(overlay.session_enabled, scope_id=session_id)

    async def is_session_blocked(self, session_id: str) -> bool:
        """Check whether all functionality is blocked for a session."""
        overlay = session_overlay_from_config(
            await self._service_config("umo", session_id)
        )
        return overlay.session_blocked

    async def is_sender_blocked(self, event: AstrMessageEvent) -> bool:
        """Check whether the inbound sender has a UID ``blocked`` overlay.

        Missing sender rows are unblocked.

        Args:
            event: Inbound event used to mint the sender key.

        Returns:
            True when the sender overlay sets ``blocked``.
        """
        overlay = sender_overlay_from_config(
            await self._service_config("sender", sender_admission_key_from_event(event))
        )
        return overlay.blocked

    async def set_sender_blocked(
        self, event_or_key: AstrMessageEvent | str, blocked: bool
    ) -> None:
        """Block or unblock an IM sender for this bot instance.

        Args:
            event_or_key: Inbound event used to mint ``Subject.im.id``, or that
                sender key itself.
            blocked: True to refuse the sender in every session.
        """
        await self._put_sender_overlay(
            self._sender_scope_id(event_or_key),
            blocked=blocked,
        )

    async def set_sender_llm_enabled(
        self, event_or_key: AstrMessageEvent | str, enabled: bool
    ) -> None:
        """Set the sender LLM overlay for this bot instance.

        Args:
            event_or_key: Inbound event used to mint ``Subject.im.id``, or that
                sender key itself.
            enabled: True to enable built-in LLM for this sender.
        """
        await self._put_sender_overlay(
            self._sender_scope_id(event_or_key),
            llm_enabled=enabled,
        )

    async def set_session_blocked(self, session_id: str, blocked: bool) -> None:
        """Block or unblock all functionality for a session."""
        session_config = await self._service_config("umo", session_id)
        session_config["session_blocked"] = blocked
        await self.preferences.put_async(
            scope="umo",
            scope_id=session_id,
            key=SESSION_SERVICE_CONFIG_KEY,
            value=session_config,
        )
