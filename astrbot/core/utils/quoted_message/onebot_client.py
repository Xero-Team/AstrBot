from collections.abc import Awaitable
from typing import Any, Protocol

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .settings import SETTINGS, QuotedMessageParserSettings


def _unwrap_action_response(ret: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ret, dict):
        return {}
    data = ret.get("data")
    if isinstance(data, dict):
        return data
    return ret


class CallAction(Protocol):
    def __call__(self, action: str, **params: Any) -> Awaitable[Any] | Any: ...


class OneBotClient:
    def __init__(
        self,
        event: AstrMessageEvent,
        settings: QuotedMessageParserSettings = SETTINGS,
    ):
        self._call_action = self._resolve_call_action(event)
        self._settings = settings

    @staticmethod
    def _resolve_call_action(event: AstrMessageEvent) -> CallAction | None:
        bot = getattr(event, "bot", None) or getattr(event, "_bot", None)
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        if not callable(call_action):
            call_action = getattr(bot, "call_action", None)
        if not callable(call_action):
            adapter = getattr(event, "adapter", None) or getattr(
                event, "_adapter", None
            )
            client = getattr(adapter, "client", None)
            if client is None:
                return None

            get_message = getattr(client, "get_message", None)
            get_forward_message = getattr(client, "get_forward_message", None)
            get_image = getattr(client, "get_image", None)
            get_file = getattr(client, "get_file", None)
            get_group_file_url = getattr(client, "get_group_file_url", None)
            get_private_file_url = getattr(client, "get_private_file_url", None)
            if (
                not callable(get_message)
                or not callable(get_forward_message)
                or not callable(get_image)
                or not callable(get_file)
                or not callable(get_group_file_url)
                or not callable(get_private_file_url)
            ):
                return None

            async def _call_action(action: str, **params: Any) -> dict[str, Any]:
                message_id = params.get("message_id", params.get("id"))

                if action == "get_msg":
                    if message_id is None:
                        raise ValueError(f"action {action} requires message_id or id")
                    fetched = await get_message(message_id)
                    return OneBotClient._build_napcat_get_msg_payload(fetched)
                if action == "get_forward_msg":
                    if message_id is None:
                        raise ValueError(f"action {action} requires message_id or id")
                    payload = await get_forward_message(message_id)
                    if not isinstance(payload, dict):
                        raise TypeError(
                            "NapCat get_forward_message did not return a dict payload"
                        )
                    return payload
                if action == "get_image":
                    return await get_image(
                        file=OneBotClient._string_or_none(params.get("file")),
                        file_id=OneBotClient._string_or_none(
                            params.get("file_id", params.get("id"))
                        ),
                    )
                if action == "get_file":
                    return await get_file(
                        file=OneBotClient._string_or_none(params.get("file")),
                        file_id=OneBotClient._string_or_none(
                            params.get("file_id", params.get("id"))
                        ),
                    )
                if action == "get_group_file_url":
                    group_id = params.get("group_id")
                    file_id = OneBotClient._string_or_none(params.get("file_id"))
                    if group_id is None or file_id is None:
                        raise ValueError(
                            "action get_group_file_url requires group_id and file_id"
                        )
                    return await get_group_file_url(
                        group_id=group_id,
                        file_id=file_id,
                    )
                if action == "get_private_file_url":
                    file_id = OneBotClient._string_or_none(params.get("file_id"))
                    if file_id is None:
                        raise ValueError("action get_private_file_url requires file_id")
                    return await get_private_file_url(file_id=file_id)
                raise ValueError(f"action {action} is not supported by NapCat client")

            return _call_action
        return call_action

    @staticmethod
    def _string_or_none(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _build_napcat_get_msg_payload(fetched: object) -> dict[str, Any]:
        sender = getattr(fetched, "extra", {}).get("sender", {})
        if not isinstance(sender, dict):
            sender = {}
        data = dict(getattr(fetched, "extra", {}))
        data["message_id"] = getattr(fetched, "message_id", 0)
        data["user_id"] = getattr(fetched, "sender_id", None)
        data["time"] = getattr(fetched, "time", None)
        data["raw_message"] = getattr(fetched, "raw_message", "") or getattr(
            fetched, "message_str", ""
        )
        data["message"] = getattr(fetched, "message_payload", None)
        data["sender"] = {
            **sender,
            **(
                {"user_id": getattr(fetched, "sender_id", None)}
                if getattr(fetched, "sender_id", None) is not None
                else {}
            ),
            **(
                {"nickname": getattr(fetched, "sender_nickname", None)}
                if getattr(fetched, "sender_nickname", None)
                else {}
            ),
        }
        return {
            "status": "ok",
            "retcode": 0,
            "data": data,
        }

    async def _call_action_try_params(
        self,
        action: str,
        params_list: list[dict[str, Any]],
        *,
        warn_on_all_failed: bool | None = None,
    ) -> dict[str, Any] | None:
        if self._call_action is None:
            return None
        if warn_on_all_failed is None:
            warn_on_all_failed = self._settings.warn_on_action_failure

        last_error: Exception | None = None
        last_params: dict[str, Any] | None = None
        for params in params_list:
            try:
                result = await self._call_action(action, **params)
                if isinstance(result, dict):
                    return result
            except Exception as exc:
                last_error = exc
                last_params = params
                logger.debug(
                    "quoted_message_parser: action %s failed with params %s: %s",
                    action,
                    {k: str(v)[:64] for k, v in params.items()},
                    exc,
                )
        if warn_on_all_failed and last_error is not None:
            logger.warning(
                "quoted_message_parser: all attempts failed for action %s, "
                "last_params=%s, error=%s",
                action,
                (
                    {k: str(v)[:64] for k, v in last_params.items()}
                    if isinstance(last_params, dict)
                    else None
                ),
                last_error,
            )
        return None

    async def call(
        self,
        action: str,
        params: dict[str, Any],
        *,
        warn_on_all_failed: bool = False,
        unwrap_data: bool = True,
    ) -> dict[str, Any] | None:
        ret = await self._call_action_try_params(
            action,
            [params],
            warn_on_all_failed=warn_on_all_failed,
        )
        if not unwrap_data:
            return ret
        return _unwrap_action_response(ret)

    async def _call_action_compat(
        self,
        action: str,
        message_id: str | int,
    ) -> dict[str, Any] | None:
        message_id_str = str(message_id).strip()
        if not message_id_str:
            return None

        params_list: list[dict[str, Any]] = [
            {"message_id": message_id_str},
            {"id": message_id_str},
        ]
        if message_id_str.isdigit():
            int_id = int(message_id_str)
            params_list.extend([{"message_id": int_id}, {"id": int_id}])
        return await self._call_action_try_params(action, params_list)

    async def get_msg(self, message_id: str | int) -> dict[str, Any] | None:
        return await self._call_action_compat("get_msg", message_id)

    async def get_msg_sender_id(self, message_id: str | int) -> str | None:
        payload = await self.get_msg(message_id)
        data = _unwrap_action_response(payload)
        sender = data.get("sender")
        if isinstance(sender, dict):
            sender_id = sender.get("user_id")
            if sender_id is not None:
                sender_text = str(sender_id).strip()
                if sender_text:
                    return sender_text

        sender_id = data.get("user_id")
        if sender_id is None:
            return None
        sender_text = str(sender_id).strip()
        return sender_text or None

    async def get_forward_msg(self, forward_id: str | int) -> dict[str, Any] | None:
        return await self._call_action_compat("get_forward_msg", forward_id)
