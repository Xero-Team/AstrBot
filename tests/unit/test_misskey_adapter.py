from asyncio import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.misskey.misskey_adapter import (
    MisskeyPlatformAdapter,
)


def make_adapter(**config):
    adapter = MisskeyPlatformAdapter({"id": "misskey-test", **config}, {}, Queue())
    adapter.api = SimpleNamespace(
        send_room_message=AsyncMock(),
        send_message=AsyncMock(),
        create_note=AsyncMock(),
        upload_and_find_file=AsyncMock(return_value={"id": "uploaded"}),
        upload_file=AsyncMock(),
    )
    return adapter


def make_session(session_id: str) -> MessageSession:
    return MessageSession("misskey-test", MessageType.FRIEND_MESSAGE, session_id)


@pytest.mark.asyncio
async def test_send_by_session_reports_uninitialized_api_and_empty_message():
    adapter = make_adapter()
    adapter.api = None

    result = await adapter.send_by_session(make_session("chat%user"), MessageChain())
    assert result and not result.success
    assert result.error_message == "Misskey API client is not initialized"

    adapter = make_adapter()
    result = await adapter.send_by_session(
        make_session("chat%user"), MessageChain([Plain(" ")])
    )
    assert result and not result.success
    assert result.error_message == "Message content is empty"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_id", "method", "payload_key"),
    [
        ("room%room-id", "send_room_message", "toRoomId"),
        ("chat%user-id", "send_message", "toUserId"),
        ("note%user-id", "create_note", "text"),
    ],
)
async def test_send_by_session_routes_room_chat_and_note(
    session_id, method, payload_key
):
    adapter = make_adapter()

    result = await adapter.send_by_session(
        make_session(session_id), MessageChain([Plain("hello")])
    )

    assert result and result.success
    call = getattr(adapter.api, method).await_args
    payload = call.args[0] if call.args else call.kwargs
    assert payload[payload_key] == (
        session_id.split("%", 1)[1] if payload_key != "text" else "hello"
    )


@pytest.mark.asyncio
async def test_send_by_session_uploads_file_falls_back_and_cleans_temp_file(
    monkeypatch, tmp_path
):
    adapter = make_adapter(misskey_upload_concurrency=0)
    temporary_file = tmp_path / "upload.bin"
    temporary_file.write_bytes(b"test")
    component = SimpleNamespace(file="upload.bin")

    async def resolve_component(_component):
        return None, str(temporary_file)

    async def upload_local(_api, _path, _name, _folder):
        return None

    async def fallback_url():
        return "https://files.example/fallback"

    component.register_to_file_service = fallback_url
    monkeypatch.setattr(
        "astrbot.core.platform.sources.misskey.misskey_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.misskey.misskey_utils.resolve_component_url_or_path",
        resolve_component,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.misskey.misskey_utils.upload_local_with_retries",
        upload_local,
    )

    result = await adapter.send_by_session(
        make_session("room%room-id"), MessageChain([Plain("hello"), component])
    )

    assert result and result.success
    assert not temporary_file.exists()
    assert adapter.api.send_room_message.await_args.args[0]["text"].endswith(
        "https://files.example/fallback"
    )


@pytest.mark.asyncio
async def test_send_by_session_reports_send_exception_and_keeps_external_file(
    monkeypatch, tmp_path
):
    adapter = make_adapter()
    adapter.api.send_message.side_effect = RuntimeError("network down")
    external_file = tmp_path / "outside.bin"
    external_file.write_bytes(b"test")
    component = SimpleNamespace(file="outside.bin")

    async def resolve_component(_component):
        return None, str(external_file)

    monkeypatch.setattr(
        "astrbot.core.platform.sources.misskey.misskey_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path / "unrelated"),
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.misskey.misskey_utils.resolve_component_url_or_path",
        resolve_component,
    )

    result = await adapter.send_by_session(
        make_session("chat%user-id"), MessageChain([Plain("hello"), component])
    )

    assert result and not result.success
    assert result.error_message == "network down"
    assert external_file.exists()
