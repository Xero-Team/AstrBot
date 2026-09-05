import inspect

import pytest
from pydantic import ValidationError

from astrbot.core.message.components import (
    Anonymous,
    BaseMessageComponent,
    ComponentTypes,
    FlashTransfer,
    Forward,
    Mention,
    MentionAll,
    Node,
    Nodes,
    OnlineFile,
    Plain,
    Poke,
    Reply,
)
from astrbot.core.message.message_event_result import MessageEventResult


@pytest.mark.asyncio
async def test_message_components_use_only_async_serialization_api():
    assert inspect.iscoroutinefunction(BaseMessageComponent.to_dict)
    assert not hasattr(BaseMessageComponent, "toDict")

    components = [
        Plain(text="mock text"),
        Anonymous(ignore=1),
        Mention(target="10001"),
        OnlineFile(
            msg_id="mock-message",
            element_id="mock-element",
            file_name="mock.txt",
            file_size="128",
            is_dir=False,
        ),
        Reply(id="mock-reply"),
        Poke(id="10002"),
        Forward(id="mock-forward"),
        FlashTransfer(file_set_id="mock-file-set"),
    ]

    payloads = [await component.to_dict() for component in components]

    assert [payload["type"] for payload in payloads] == [
        "text",
        "anonymous",
        "mention",
        "onlinefile",
        "reply",
        "poke",
        "forward",
        "flashtransfer",
    ]
    assert all(not hasattr(component, "toDict") for component in components)


@pytest.mark.asyncio
async def test_nested_nodes_use_async_component_serialization():
    node = Node(
        uin="10001",
        name="Mock Sender",
        content=[Forward(id="mock-forward"), Plain(text="mock content")],
    )

    payload = await Nodes(nodes=[node]).to_dict()

    assert payload == {
        "messages": [
            {
                "type": "node",
                "data": {
                    "user_id": "10001",
                    "nickname": "Mock Sender",
                    "content": [
                        {"type": "forward", "data": {"id": "mock-forward"}},
                        {"type": "text", "data": {"text": "mock content"}},
                    ],
                },
            }
        ]
    }


@pytest.mark.asyncio
async def test_mention_to_dict_is_platform_neutral():
    payload = await Mention(target="10001").to_dict()
    assert payload == {"type": "mention", "data": {"target": "10001"}}


@pytest.mark.asyncio
async def test_mention_all_to_dict_is_platform_neutral():
    payload = await MentionAll().to_dict()
    assert payload == {"type": "mention_all", "data": {}}


def test_mention_rejects_qq_keyword():
    with pytest.raises(ValidationError):
        Mention(qq="10001")


def test_mention_all_is_not_a_mention_subclass():
    assert not issubclass(MentionAll, Mention)
    assert not isinstance(MentionAll(), Mention)


def test_message_event_result_mention_builders():
    result = MessageEventResult().mention("n", "1").mention_all()
    assert [type(item) for item in result.chain] == [Mention, MentionAll]


def test_component_types_maps_mention_keys_only():
    assert ComponentTypes["mention"] is Mention
    assert ComponentTypes["mention_all"] is MentionAll
    assert "at" not in ComponentTypes


@pytest.mark.asyncio
async def test_node_to_dict_maps_mentions_to_onebot_at():
    node = Node(
        uin="10001",
        name="Mock Sender",
        content=[Mention(target="10002"), MentionAll(), Plain(text="hi")],
    )

    payload = await node.to_dict()

    assert payload == {
        "type": "node",
        "data": {
            "user_id": "10001",
            "nickname": "Mock Sender",
            "content": [
                {"type": "at", "data": {"qq": "10002"}},
                {"type": "at", "data": {"qq": "all"}},
                {"type": "text", "data": {"text": "hi"}},
            ],
        },
    }
