from __future__ import annotations

import asyncio
import json

import pytest

from astrbot.core.platform.sources.misskey.misskey_api import StreamingClient


class _AsyncWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self._messages = iter(messages)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._messages)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.mark.asyncio
async def test_misskey_streaming_client_listen_background_dispatches_handlers():
    client = StreamingClient("https://example.test", "token-1")
    client.is_connected = True
    client._running = True
    client.channels["channel-1"] = "main"

    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()

    async def _handler(event_body: dict) -> None:
        if event_body.get("id") == "first":
            first_started.set()
            await release_first.wait()
            return
        if event_body.get("id") == "second":
            second_started.set()

    client.add_message_handler("main:note", _handler)
    client.websocket = _AsyncWebSocket(
        [
            json.dumps(
                {
                    "type": "channel",
                    "body": {
                        "id": "channel-1",
                        "type": "note",
                        "body": {"id": "first"},
                    },
                }
            ),
            json.dumps(
                {
                    "type": "channel",
                    "body": {
                        "id": "channel-1",
                        "type": "note",
                        "body": {"id": "second"},
                    },
                }
            ),
        ]
    )

    listen_task = asyncio.create_task(client.listen())
    await asyncio.wait_for(first_started.wait(), timeout=1.0)
    await asyncio.wait_for(second_started.wait(), timeout=1.0)
    release_first.set()
    await listen_task
