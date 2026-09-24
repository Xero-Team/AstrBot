from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest

from astrbot.core.message.components import Forward, Node, Nodes, Plain
from astrbot.core.platform.onebot_forward import expand_unexpanded_forwards

pytestmark = pytest.mark.platform


def _node(name: str, uin: str, *content) -> Node:
    return Node(name=name, uin=uin, content=list(content))


@pytest.mark.asyncio
async def test_expands_id_only_forward_into_nodes() -> None:
    async def fetch(forward_id: str) -> Mapping[str, object]:
        assert forward_id == "f1"
        return {
            "data": {
                "messages": [{"user_id": "1", "nickname": "Alice", "message": "hi"}]
            }
        }

    async def parse(payload: Mapping[str, object]) -> list:
        raw = payload["data"]["messages"]
        return [
            _node(item["nickname"], item["user_id"], Plain(item["message"]))
            for item in raw
        ]

    forward = Forward(id="f1", content=None)
    out = await expand_unexpanded_forwards([forward], fetch=fetch, parse=parse)

    assert len(out) == 1
    assert isinstance(out[0], Forward)
    assert out[0].content is not None
    assert isinstance(out[0].content[0], Node)
    assert out[0].content[0].name == "Alice"


@pytest.mark.asyncio
async def test_expands_nested_forwards_until_budget_exhausted() -> None:
    async def fetch(forward_id: str) -> Mapping[str, object]:
        return {"data": {"messages": [{"id": forward_id}]}}

    async def parse(payload: Mapping[str, object]) -> list:
        marker = payload["data"]["messages"][0]["id"]
        if marker == "root":
            return [_node("A", "1", Forward(id="nested", content=None))]
        return [_node("B", "2", Plain("leaf"))]

    root = Forward(id="root", content=None)
    out = await expand_unexpanded_forwards([root], fetch=fetch, parse=parse)
    nested = out[0].content[0].content[0]
    assert isinstance(nested, Forward)
    assert nested.content is not None
    assert nested.content[0].name == "B"

    limited = await expand_unexpanded_forwards(
        [Forward(id="root", content=None)], fetch=fetch, parse=parse, max_fetch=1
    )
    nested_limited = limited[0].content[0].content[0]
    assert isinstance(nested_limited, Forward)
    assert nested_limited.content is None


@pytest.mark.asyncio
async def test_same_forward_id_is_fetched_once() -> None:
    calls: list[str] = []

    async def fetch(forward_id: str) -> Mapping[str, object]:
        calls.append(forward_id)
        return {
            "data": {"messages": [{"user_id": "1", "nickname": "A", "message": "x"}]}
        }

    async def parse(payload: Mapping[str, object]) -> list:
        return [_node("A", "1", Plain("x"))]

    out = await expand_unexpanded_forwards(
        [Forward(id="a", content=None), Forward(id="a", content=None)],
        fetch=fetch,
        parse=parse,
    )
    assert calls == ["a"]
    assert all(isinstance(item, Forward) and item.content for item in out)


@pytest.mark.asyncio
async def test_fetch_failure_preserves_original_forward() -> None:
    async def fetch(forward_id: str) -> Mapping[str, object]:
        raise RuntimeError("boom")

    async def parse(payload: Mapping[str, object]) -> list:
        raise AssertionError("parse must not run after a fetch failure")

    forward = Forward(id="f", content=None)
    out = await expand_unexpanded_forwards([forward], fetch=fetch, parse=parse)
    assert out == [forward]
    assert out[0].content is None


@pytest.mark.asyncio
async def test_fetch_timeout_preserves_original_forward() -> None:
    async def fetch(forward_id: str) -> Mapping[str, object]:
        await asyncio.sleep(0.05)
        return {
            "data": {"messages": [{"user_id": "1", "nickname": "A", "message": "x"}]}
        }

    async def parse(payload: Mapping[str, object]) -> list:
        return [_node("A", "1", Plain("x"))]

    forward = Forward(id="f", content=None)
    out = await expand_unexpanded_forwards(
        [forward], fetch=fetch, parse=parse, timeout=0.001
    )
    assert out == [forward]


@pytest.mark.asyncio
async def test_empty_parse_preserves_original_forward() -> None:
    async def fetch(forward_id: str) -> Mapping[str, object]:
        return {"data": {"messages": []}}

    async def parse(payload: Mapping[str, object]) -> list:
        return []

    forward = Forward(id="f", content=None)
    out = await expand_unexpanded_forwards([forward], fetch=fetch, parse=parse)
    assert out == [forward]


@pytest.mark.asyncio
async def test_recurses_into_nodes_and_keeps_other_components() -> None:
    async def fetch(forward_id: str) -> Mapping[str, object]:
        return {
            "data": {"messages": [{"user_id": "1", "nickname": "A", "message": "x"}]}
        }

    async def parse(payload: Mapping[str, object]) -> list:
        return [_node("A", "1", Plain("x"))]

    tree = [
        Plain("before"),
        Nodes(nodes=[_node("A", "1", Forward(id="f", content=None))]),
    ]
    out = await expand_unexpanded_forwards(tree, fetch=fetch, parse=parse)
    assert out[0].text == "before"
    assert isinstance(out[1], Nodes)
    nested = out[1].nodes[0].content[0]
    assert isinstance(nested, Forward)
    assert nested.content is not None


@pytest.mark.asyncio
async def test_zero_budget_leaves_forwards_unexpanded() -> None:
    async def fetch(forward_id: str) -> Mapping[str, object]:
        raise AssertionError("must not fetch with max_fetch=0")

    async def parse(payload: Mapping[str, object]) -> list:
        raise AssertionError("must not parse with max_fetch=0")

    forward = Forward(id="f", content=None)
    out = await expand_unexpanded_forwards(
        [forward], fetch=fetch, parse=parse, max_fetch=0
    )
    assert out == [forward]
