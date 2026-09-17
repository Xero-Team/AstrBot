"""会话服务管理器 - 负责管理每个会话的LLM、TTS等服务的启停状态"""

from astrbot import logger
from astrbot.core.auth.admission import (
    SESSION_SERVICE_CONFIG_KEY,
    composed_llm_enabled,
    sender_admission_key_from_event,
    sender_overlay_from_config,
    session_admission_key_from_event,
    session_overlay_from_config,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.shared_preferences import SharedPreferences


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

    async def is_llm_enabled_for_session(self, session_id: str) -> bool:
        """检查LLM是否在指定会话中启用

        Args:
            session_id: 会话ID (unified_msg_origin)

        Returns:
            bool: True表示启用，False表示禁用

        """
        overlay = session_overlay_from_config(
            await self._service_config("umo", session_id)
        )
        return True if overlay.llm_enabled is None else overlay.llm_enabled

    async def set_llm_status_for_session(self, session_id: str, enabled: bool) -> None:
        """设置LLM在指定会话中的启停状态

        Args:
            session_id: 会话ID (unified_msg_origin)
            enabled: True表示启用，False表示禁用

        """
        session_config = await self._service_config("umo", session_id)
        session_config["llm_enabled"] = enabled
        await self.preferences.put_async(
            scope="umo",
            scope_id=session_id,
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
        return composed_llm_enabled(session_overlay, sender_overlay)

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
        return tts_enabled if isinstance(tts_enabled, bool) else True

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
        return True if overlay.session_enabled is None else overlay.session_enabled

    async def is_session_blocked(self, session_id: str) -> bool:
        """Check whether all functionality is blocked for a session."""
        overlay = session_overlay_from_config(
            await self._service_config("umo", session_id)
        )
        return overlay.session_blocked

    async def is_sender_blocked(self, event: AstrMessageEvent) -> bool:
        """Check whether the inbound sender has a UID ``blocked`` overlay.

        ``scope=sender`` is readable in this slice; missing rows are unblocked.

        Args:
            event: Inbound event used to mint the sender key.

        Returns:
            True when the sender overlay sets ``blocked``.
        """
        overlay = sender_overlay_from_config(
            await self._service_config("sender", sender_admission_key_from_event(event))
        )
        return overlay.blocked

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
