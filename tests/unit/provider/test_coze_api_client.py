from collections.abc import AsyncIterator

import pytest

from astrbot.core.agent.runners.coze.coze_api_client import CozeAPIClient


class _Content:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


class _Response:
    status = 200

    def __init__(self, chunks: list[bytes]) -> None:
        self.content = _Content(chunks)

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def post(self, *_args: object, **_kwargs: object) -> _Response:
        return _Response(self._chunks)


def _client(chunks: list[bytes]) -> CozeAPIClient:
    client = CozeAPIClient("key")

    async def _ensure_session() -> _Session:
        return _Session(chunks)

    client._ensure_session = _ensure_session  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_chat_messages_flushes_a_final_event_without_trailing_newline():
    client = _client([b'event: message\ndata: {"content": "hello"}'])

    events = [
        event async for event in client.chat_messages(bot_id="bot", user_id="user")
    ]

    assert events == [{"event": "message", "data": {"content": "hello"}}]


@pytest.mark.asyncio
async def test_chat_messages_flushes_a_final_data_line_after_a_delimited_event():
    client = _client(
        [
            b'event: message\ndata: {"content": "first"}\n\n',
            b'event: message\ndata: {"content": "second"}',
        ]
    )

    events = [
        event async for event in client.chat_messages(bot_id="bot", user_id="user")
    ]

    assert events == [
        {"event": "message", "data": {"content": "first"}},
        {"event": "message", "data": {"content": "second"}},
    ]
