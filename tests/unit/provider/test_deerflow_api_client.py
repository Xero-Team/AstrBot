import pytest

from astrbot.core.agent.runners.deerflow.deerflow_api_client import (
    DeerFlowAPIClient,
    DeerFlowAPIError,
)


class _FakeDeleteResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _ = exc_type, exc, tb

    async def text(self) -> str:
        return self._body


class _FakeSession:
    def __init__(self, response: _FakeDeleteResponse):
        self.closed = False
        self._response = response

    def delete(self, *args, **kwargs):
        _ = args, kwargs
        return self._response


@pytest.mark.asyncio
async def test_delete_thread_raises_api_error_with_thread_context():
    client = DeerFlowAPIClient(api_base="http://127.0.0.1:2026")
    client._session = _FakeSession(
        _FakeDeleteResponse(status=500, body="thread cleanup failed"),
    )

    try:
        with pytest.raises(DeerFlowAPIError) as exc_info:
            await client.delete_thread("thread-123")
    finally:
        client._closed = True

    assert exc_info.value.status == 500
    assert exc_info.value.thread_id == "thread-123"
    assert "/api/threads/thread-123" in str(exc_info.value)
    assert "thread cleanup failed" in str(exc_info.value)


class _ChunkedContent:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def iter_chunked(self, size: int):
        _ = size
        for chunk in self._chunks:
            yield chunk


class _StreamResponse:
    def __init__(self, chunks: list[bytes]):
        self.content = _ChunkedContent(chunks)


@pytest.mark.asyncio
async def test_stream_sse_normalizes_crlf_split_across_chunks():
    from astrbot.core.agent.runners.deerflow.deerflow_api_client import _stream_sse

    response = _StreamResponse(
        [b"event: values\r", b'\ndata: {"a": 1}\n\n'],
    )

    events = [event async for event in _stream_sse(response)]

    assert events == [{"event": "values", "data": {"a": 1}}]
