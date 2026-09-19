from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.platform.message_capabilities import MESSAGE_CAPABILITIES
from astrbot.core.platform.message_delivery import plan_message_delivery
from astrbot.core.platform.message_i18n import LOCALES
from astrbot.core.platform.message_protocol import (
    ContentKind,
    MediaReference,
    MessageDeliveryCapabilities,
    MessageEnvelope,
    NativeContent,
    PortablePart,
    SenderSnapshot,
    plan_delivery,
)
from astrbot.core.platform.message_renderers import render_source_header
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.route_identity import PlatformRouteIdentity
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.platform.session_bridge import SessionBridgeManager
from tests.unit.test_session_bridge import FakeSessionBridgeStore


def test_message_i18n_catalogs_share_keys():
    assert set(LOCALES["zh-CN"]) == set(LOCALES["en-US"])


def test_plan_delivery_merges_adjacent_text_parts():
    envelope = MessageEnvelope(
        source_route=PlatformRouteIdentity("napcat", MessageType.GROUP_MESSAGE, "1"),
        content=(
            PortablePart(ContentKind.TEXT, "[来自 NapCat 群聊 · Alice]\n"),
            PortablePart(ContentKind.TEXT, "正文"),
        ),
    )

    batches = plan_delivery(envelope, MessageDeliveryCapabilities())

    assert len(batches) == 1
    assert len(batches[0].parts) == 1
    assert batches[0].parts[0].value == "[来自 NapCat 群聊 · Alice]\n正文"


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("napcat", "[来自 NapCat 群聊 · Alice]\n"),
        ("telegram", "来自 Alice（napcat）\n"),
        ("discord", "**来自 Alice（napcat）**\n"),
        ("slack", "来自 Alice（napcat）\n"),
        ("line", "[来自 Alice（napcat）]\n"),
        ("webchat", "[来自 napcat · Alice]\n"),
    ],
)
def test_source_header_renderer_uses_target_style(target, expected):
    envelope = MessageEnvelope(
        source_route=PlatformRouteIdentity("napcat", MessageType.GROUP_MESSAGE, "1"),
        sender=SenderSnapshot("42", "Alice", "napcat"),
    )

    assert render_source_header(envelope, target) == expected


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("napcat", "[From NapCat group · Alice]\n"),
        ("telegram", "From Alice (napcat)\n"),
        ("discord", "**From Alice (napcat)**\n"),
        ("slack", "From Alice (napcat)\n"),
        ("line", "[From Alice (napcat)]\n"),
        ("webchat", "[From napcat · Alice]\n"),
    ],
)
def test_source_header_renderer_uses_english_locale(target, expected):
    envelope = MessageEnvelope(
        source_route=PlatformRouteIdentity("napcat", MessageType.GROUP_MESSAGE, "1"),
        sender=SenderSnapshot("42", "Alice", "napcat"),
    )

    assert render_source_header(envelope, target, "en-US") == expected


def _route() -> PlatformRouteIdentity:
    return PlatformRouteIdentity("source", MessageType.FRIEND_MESSAGE, "sender")


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path, monkeypatch):
    from astrbot.core.platform import message_media
    from astrbot.core.utils import astrbot_path

    monkeypatch.setattr(
        astrbot_path, "get_astrbot_temp_path", lambda: str(tmp_path / "runtime")
    )
    monkeypatch.setattr(
        message_media, "get_astrbot_temp_path", lambda: str(tmp_path / "runtime")
    )


def _event(umo="source:FriendMessage:sender", *, sender="actor", components=()):
    from astrbot.core.platform.message_session import MessageSession

    subject = Subject.im(
        platform_instance="source", bot_account_id="bot", sender_id=sender
    )
    session = MessageSession.from_str(umo)
    return SimpleNamespace(
        unified_msg_origin=umo,
        subject=subject,
        auth_context=AuthContext(
            subject=subject,
            source="im",
            config_id="default",
            authenticated=True,
            origin_session_resource_id=Resource.session("default", umo).id,
        ),
        route_identity=PlatformRouteIdentity(
            session.platform_id, session.message_type, session.session_id
        ),
        get_messages=lambda: list(components),
        get_platform_name=lambda: "telegram",
        get_sender_id=lambda: sender,
        get_sender_name=lambda: sender,
        get_self_id=lambda: "bot",
        message_obj=SimpleNamespace(message_id="inbound"),
        created_at=0.0,
    )


def _manager(send=None):
    authorization = SimpleNamespace(
        authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
    )
    sender = send or AsyncMock(
        return_value=PlatformSendResult("target", True, "target", message_ids=("sent",))
    )
    manager = SessionBridgeManager(
        sender,
        lambda _: MessageDeliveryCapabilities(quote=True, media=frozenset({"image"})),
        authorization=authorization,
        get_config_id=lambda _: "default",
        store=FakeSessionBridgeStore(),
    )
    return manager, authorization, sender


def test_plan_delivery_preserves_order_when_target_cannot_mix_media() -> None:
    envelope = MessageEnvelope(
        source_route=_route(),
        content=(
            PortablePart(ContentKind.TEXT, "before"),
            PortablePart(ContentKind.IMAGE, MediaReference("file:///image.jpg")),
            PortablePart(ContentKind.TEXT, "after"),
        ),
    )

    batches = plan_delivery(
        envelope,
        MessageDeliveryCapabilities(media=frozenset({"image"}), mixed_parts=False),
    )

    assert [[part.value for part in batch.parts] for batch in batches] == [
        ["before"],
        [MediaReference("file:///image.jpg")],
        ["after"],
    ]


def test_plan_delivery_falls_back_for_unknown_native_content() -> None:
    envelope = MessageEnvelope(
        source_route=_route(),
        content=(NativeContent("telegram", "mini_app", "{}", "Open this link"),),
    )

    batches = plan_delivery(envelope, MessageDeliveryCapabilities())

    assert batches[0].parts == (PortablePart(ContentKind.TEXT, "Open this link"),)


def test_plan_delivery_keeps_supported_native_content_as_its_own_batch() -> None:
    native = NativeContent("napcat", "mini_app", '{"data": "{}"}')
    envelope = MessageEnvelope(source_route=_route(), content=(native,))

    batches = plan_delivery(
        envelope,
        MessageDeliveryCapabilities(
            native_namespaces=frozenset({"napcat"}),
            native_kinds=frozenset({"mini_app"}),
        ),
    )

    assert len(batches) == 1
    assert batches[0].native == (native,)


def test_bundled_platform_capabilities_cover_all_adapter_families() -> None:
    expected = {
        "aiocqhttp",
        "napcat",
        "telegram",
        "discord",
        "kook",
        "lark",
        "line",
        "mattermost",
        "misskey",
        "satori",
        "slack",
        "dingtalk",
        "qqofficial",
        "qqofficial_webhook",
        "webchat",
        "wecom",
        "wecom_ai_bot",
        "weixin_oc",
        "weixin_official_account",
    }
    assert set(MESSAGE_CAPABILITIES) == expected
    assert MESSAGE_CAPABILITIES["webchat"].forward is False


def test_line_and_slack_capabilities_match_message_payload_limits() -> None:
    assert MESSAGE_CAPABILITIES["line"].media == frozenset(
        {"image", "audio", "video", "file"}
    )
    assert MESSAGE_CAPABILITIES["slack"].max_text_length == 3000


def test_delivery_planner_converts_media_to_existing_components() -> None:
    envelope = MessageEnvelope(
        source_route=_route(),
        content=(
            PortablePart(ContentKind.TEXT, "caption"),
            PortablePart(
                ContentKind.IMAGE,
                MediaReference("file:///tmp/image.jpg", mime_type="image/jpeg"),
            ),
        ),
    )

    chains = plan_message_delivery(
        envelope,
        MessageDeliveryCapabilities(media=frozenset({"image"}), mixed_parts=True),
    )

    assert [type(component).__name__ for component in chains[0].chain] == [
        "Plain",
        "Image",
    ]


@pytest.mark.asyncio
async def test_session_bridge_forwards_to_matching_source() -> None:
    sent = []

    async def send(session, chain):
        sent.append((str(session), chain.get_plain_text()))
        return PlatformSendResult(session.platform_id, True, str(session))

    manager = SessionBridgeManager(
        send,
        lambda _platform: MessageDeliveryCapabilities(),
        authorization=SimpleNamespace(
            authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
        ),
        get_config_id=lambda _: "default",
        store=FakeSessionBridgeStore(),
    )
    source = "webchat:FriendMessage:source"
    target = "telegram:GroupMessage:target"
    await manager.watch(_event(source), target)
    await manager.observe(
        MessageEnvelope(
            source_route=PlatformRouteIdentity(
                "telegram", MessageType.GROUP_MESSAGE, "target"
            ),
            source_message_id="42",
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )
    await manager.observe(
        MessageEnvelope(
            source_route=PlatformRouteIdentity(
                "telegram", MessageType.GROUP_MESSAGE, "target"
            ),
            source_message_id="42",
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )

    assert sent == [(source, "[来自 telegram · 未知]\nhello")]
    await manager.terminate()


@pytest.mark.asyncio
async def test_session_bridge_header_follows_target_locale() -> None:
    sent = []

    async def send(session, chain):
        sent.append(chain.get_plain_text())
        return PlatformSendResult(session.platform_id, True, str(session))

    manager = SessionBridgeManager(
        send,
        lambda _platform: MessageDeliveryCapabilities(),
        authorization=SimpleNamespace(
            authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
        ),
        get_config_id=lambda _: "default",
        get_locale=AsyncMock(return_value="en-US"),
        store=FakeSessionBridgeStore(),
    )
    source = "webchat:FriendMessage:source"
    target = "telegram:GroupMessage:target"
    await manager.watch(_event(source), target)
    await manager.observe(
        MessageEnvelope(
            source_route=PlatformRouteIdentity(
                "telegram", MessageType.GROUP_MESSAGE, "target"
            ),
            source_message_id="42",
            sender=SenderSnapshot("1", "Alice", "telegram"),
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )

    assert sent == ["[From telegram · Alice]\nhello"]
    await manager.terminate()


@pytest.mark.asyncio
async def test_session_bridge_header_uses_adapter_family_not_instance_id() -> None:
    sent = []

    async def send(session, chain):
        sent.append(chain.get_plain_text())
        return PlatformSendResult(session.platform_id, True, str(session))

    manager = SessionBridgeManager(
        send,
        lambda _platform: MessageDeliveryCapabilities(),
        authorization=SimpleNamespace(
            authorize=AsyncMock(return_value=SimpleNamespace(allowed=True))
        ),
        get_config_id=lambda _: "default",
        get_platform_family=lambda umo: {
            "tg-main:FriendMessage:source": "telegram",
        }.get(umo, umo.split(":", 1)[0]),
        store=FakeSessionBridgeStore(),
    )
    source = "tg-main:FriendMessage:source"
    target = "napcat:GroupMessage:room"
    await manager.watch(_event(source), target)
    await manager.observe(
        MessageEnvelope(
            source_route=PlatformRouteIdentity(
                "napcat", MessageType.GROUP_MESSAGE, "room"
            ),
            source_message_id="7",
            sender=SenderSnapshot("1", "Alice", "napcat"),
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )

    assert sent == ["来自 Alice（napcat）\nhello"]
    await manager.terminate()


@pytest.mark.asyncio
async def test_watch_checks_both_resources_and_revocation_stops_delivery():
    manager, authorization, send = _manager()
    event = _event()
    target = "target:GroupMessage:room"
    await manager.watch(event, target)
    assert [call.args[2].umo for call in authorization.authorize.await_args_list] == [
        event.unified_msg_origin,
        target,
    ]
    authorization.authorize.return_value.allowed = False
    await manager.observe(
        MessageEnvelope(
            PlatformRouteIdentity("target", MessageType.GROUP_MESSAGE, "room"),
            content=(PortablePart(ContentKind.TEXT, "secret"),),
        )
    )
    send.assert_not_awaited()
    assert await manager.list_watches(event) == ()
    await manager.terminate()


@pytest.mark.asyncio
async def test_watch_rejects_missing_identity_and_denied_target():
    manager, authorization, _ = _manager()
    event = _event()
    event.subject = None
    with pytest.raises(PermissionError):
        await manager.watch(event, "target:GroupMessage:room")
    authorization.authorize.side_effect = [
        SimpleNamespace(allowed=True),
        SimpleNamespace(allowed=False),
    ]
    with pytest.raises(PermissionError):
        await manager.watch(_event(), "target:GroupMessage:room")
    assert await manager.list_watches(_event()) == ()
    event = _event()
    event.subject = None
    with pytest.raises(PermissionError):
        await manager.unwatch(event, "target:GroupMessage:room")
    with pytest.raises(PermissionError):
        await manager.list_watches(event)
    await manager.terminate()


@pytest.mark.asyncio
async def test_watch_ownership_includes_both_source_and_actor():
    manager, _, _ = _manager()
    target = "target:GroupMessage:room"
    first, second = _event(), _event("source:FriendMessage:second")
    await manager.watch(first, target)
    await manager.watch(second, target)
    assert not await manager.unwatch(_event(sender="other"), target)
    assert len(await manager.list_watches(first)) == 1
    assert (
        len(
            await manager.list_watches(
                first,
                source_umo=second.unified_msg_origin,
            )
        )
        == 1
    )
    assert await manager.unwatch(first, target)
    assert len(await manager.list_watches(second)) == 1
    await manager.terminate()


def test_send_projection_preserves_interleaved_body_without_mutating_event():
    from astrbot.core.message.components import Image, Mention, Plain, Reply
    from astrbot.core.platform.message_projection import envelope_from_send_event

    components = [
        Mention(target="bot"),
        Reply(id="quoted", message_str="original"),
        Plain("/send target:GroupMessage:"),
        Plain("room before"),
        Image(file="base64://aGVsbG8="),
        Plain(" after"),
    ]
    event = _event(components=components)
    envelope = envelope_from_send_event(event, "target:GroupMessage:room")
    assert [part.kind for part in envelope.content] == [
        ContentKind.TEXT,
        ContentKind.IMAGE,
        ContentKind.TEXT,
    ]
    assert [
        part.value for part in envelope.content if part.kind == ContentKind.TEXT
    ] == ["before", " after"]
    assert envelope.quote.message_id == "quoted"
    assert components[2].text == "/send target:GroupMessage:"
    with pytest.raises(ValueError):
        envelope_from_send_event(event, "different:GroupMessage:room")


@pytest.mark.asyncio
async def test_send_checks_authority_before_resolving_media():
    from astrbot.core.message.components import Image, Plain

    image = Image()
    resolver = AsyncMock(return_value="base64://aGVsbG8=")
    image.set_source_resolver(resolver)
    event = _event(components=[Plain("/send target:GroupMessage:room "), image])
    manager, authorization, send = _manager()
    authorization.authorize.return_value.allowed = False
    with pytest.raises(PermissionError):
        await manager.send(event, "target:GroupMessage:room")
    resolver.assert_not_awaited()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_partial_receipt_stops_remaining_batches(tmp_path):
    from astrbot.core.message.components import Image, Plain

    media = tmp_path / "image.png"
    media.write_bytes(b"image")
    sender = AsyncMock(
        side_effect=[
            PlatformSendResult("target", True, "room", message_ids=("1",)),
            PlatformSendResult("target", False, "room"),
        ]
    )
    manager, _, _ = _manager(sender)
    event = _event(
        components=[
            Plain("/send target:GroupMessage:room before"),
            Image.fromFileSystem(media),
            Plain("after"),
        ]
    )
    receipt = await manager.send(event, "target:GroupMessage:room")
    assert receipt.status == "partial"
    assert receipt.message_ids == ("1",)
    assert sender.await_count == 2


@pytest.mark.asyncio
async def test_reply_to_forward_maps_back_to_original_message():
    from astrbot.core.message.components import Plain, Reply

    manager, _, sender = _manager()
    event = _event()
    await manager.watch(event, "target:GroupMessage:room")
    await manager.observe(
        MessageEnvelope(
            PlatformRouteIdentity("target", MessageType.GROUP_MESSAGE, "room"),
            source_message_id="original",
            content=(PortablePart(ContentKind.TEXT, "hello"),),
        )
    )
    command = _event(
        components=[
            Reply(id="sent", message_str="hello"),
            Plain("/send target:GroupMessage:room answer"),
        ]
    )
    await manager.send(command, "target:GroupMessage:room")
    chain = sender.await_args.args[1].chain
    assert isinstance(chain[0], Reply)
    assert chain[0].id == "original"
    await manager.terminate()


def test_target_limits_include_quote_fallback_and_unicode():
    from astrbot.core.platform.message_protocol import QuoteReference

    envelope = MessageEnvelope(
        _route(),
        content=(PortablePart(ContentKind.TEXT, "a😀bc😀"),),
        quote=QuoteReference(_route(), "unmapped", preview="quoted"),
    )
    chains = plan_message_delivery(
        envelope, MessageDeliveryCapabilities(max_text_length=4)
    )
    values = ["".join(component.text for component in chain.chain) for chain in chains]
    assert "".join(values) == "> quoted\na😀bc😀"
    assert all(len(value.encode("utf-16-le")) // 2 <= 4 for value in values)


def test_cross_session_mentions_are_inert_and_part_limit_is_enforced():
    from astrbot.core.message.components import Plain

    envelope = MessageEnvelope(
        _route(),
        content=(
            PortablePart(ContentKind.MENTION_ALL, "all", "@all"),
            PortablePart(ContentKind.TEXT, "text"),
            PortablePart(ContentKind.TEXT, "tail"),
        ),
    )
    chains = plan_message_delivery(
        envelope,
        MessageDeliveryCapabilities(mention=True, max_parts_per_request=2),
        target_umo="target:GroupMessage:room",
    )
    assert [len(chain.chain) for chain in chains] == [1]
    assert all(
        isinstance(component, Plain) for chain in chains for component in chain.chain
    )


@pytest.mark.asyncio
async def test_media_lease_resolves_at_source_and_cleans_only_owned_files(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from astrbot.core.message.components import Image, Plain
    from astrbot.core.platform import message_media
    from astrbot.core.platform.message_projection import envelope_from_send_event
    from astrbot.core.utils.media_utils import file_uri_to_path

    monkeypatch.setattr(
        message_media, "get_astrbot_temp_path", lambda: str(tmp_path / "runtime")
    )
    original = tmp_path / "original.png"
    original.write_bytes(b"image")
    image = Image()
    resolver = AsyncMock(return_value=str(original))
    image.set_source_resolver(resolver)
    envelope = envelope_from_send_event(
        _event(components=[Plain("/send target:GroupMessage:room "), image]),
        "target:GroupMessage:room",
    )
    async with message_media.materialize_message_media(
        envelope, MessageDeliveryCapabilities(media=frozenset({"image"}))
    ) as resolved:
        owned = Path(file_uri_to_path(resolved.content[0].value.uri))
        assert owned != original
        assert owned.read_bytes() == b"image"
        assert not image.file
    assert not owned.exists()
    assert original.exists()
    resolver.assert_awaited_once()


@pytest.mark.asyncio
async def test_media_lease_detects_image_suffix_for_extensionless_http(
    tmp_path, monkeypatch
):
    from io import BytesIO
    from pathlib import Path

    from PIL import Image as PILImage

    import astrbot.core.utils.media_utils as media_utils
    from astrbot.core.platform import message_media
    from astrbot.core.utils.media_utils import file_uri_to_path

    monkeypatch.setattr(media_utils, "get_astrbot_temp_path", lambda: str(tmp_path))
    image_buffer = BytesIO()
    PILImage.new("RGB", (1, 1), (255, 0, 0)).save(image_buffer, format="GIF")

    async def fake_download_file(_url: str, target_path: str) -> None:
        Path(target_path).write_bytes(image_buffer.getvalue())

    monkeypatch.setattr(media_utils, "download_file", fake_download_file)

    envelope = MessageEnvelope(
        _route(),
        content=(
            PortablePart(
                ContentKind.IMAGE,
                MediaReference(
                    "https://multimedia.nt.qq.com.cn/download?fileid=example"
                ),
            ),
        ),
    )
    async with message_media.materialize_message_media(
        envelope, MessageDeliveryCapabilities(media=frozenset({"image"}))
    ) as resolved:
        reference = resolved.content[0].value
        owned = Path(file_uri_to_path(reference.uri))
        assert owned.suffix == ".gif"
        assert reference.file_name == "image.gif"
        assert reference.mime_type == "image/gif"
        with PILImage.open(owned) as resolved_img:
            assert resolved_img.format == "GIF"
    assert not owned.exists()


@pytest.mark.asyncio
async def test_media_resolution_failure_preserves_order_and_hides_credentials():
    from astrbot.core.platform.message_media import materialize_message_media

    resolver = AsyncMock(side_effect=ValueError("https://private/?token=secret"))
    envelope = MessageEnvelope(
        _route(),
        content=(
            PortablePart(ContentKind.TEXT, "before"),
            PortablePart(
                ContentKind.IMAGE,
                MediaReference("", resolve_source=resolver),
            ),
            PortablePart(ContentKind.TEXT, "after"),
        ),
    )
    async with materialize_message_media(
        envelope, MessageDeliveryCapabilities(media=frozenset({"image"}))
    ) as result:
        assert [part.value for part in result.content] == [
            "before",
            "[图片]（无法获取）",
            "after",
        ]
    async with materialize_message_media(
        envelope,
        MessageDeliveryCapabilities(media=frozenset({"image"})),
        locale="en-US",
    ) as result:
        assert [part.value for part in result.content] == [
            "before",
            "[Image] (unavailable)",
            "after",
        ]


@pytest.mark.asyncio
async def test_media_resolution_failure_preserves_sender():
    from astrbot.core.message.components import Plain
    from astrbot.core.platform.message_media import materialize_message_media

    sender = SenderSnapshot("1001", "Alice", "napcat")
    resolver = AsyncMock(side_effect=ValueError("https://private/?token=secret"))
    envelope = MessageEnvelope(
        _route(),
        content=(
            PortablePart(ContentKind.TEXT, "[Alice]\n", sender=sender),
            PortablePart(
                ContentKind.IMAGE,
                MediaReference("", resolve_source=resolver),
                sender=sender,
            ),
            PortablePart(ContentKind.TEXT, "after", sender=sender),
        ),
    )
    async with materialize_message_media(
        envelope, MessageDeliveryCapabilities(media=frozenset({"image"}))
    ) as result:
        assert result.content[1].kind == ContentKind.TEXT
        assert result.content[1].sender == sender
        chains = plan_message_delivery(
            result,
            MESSAGE_CAPABILITIES["napcat"],
            target_umo="napcat:GroupMessage:room",
        )
        nodes = _forward_nodes(chains)
        assert len(nodes) == 1
        texts = [
            part.text for part in nodes[0].nodes[0].content if isinstance(part, Plain)
        ]
        assert any("无法获取" in text for text in texts)
        assert "after" in texts


def test_forwarded_transcripts_preserve_authors_and_nested_media():
    from astrbot.core.message.components import Image, Node, Nodes, Plain
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(
        _event(
            components=[
                Nodes(
                    nodes=[
                        Node(
                            name="Alice",
                            content=[
                                Plain("before"),
                                Image(file="base64://aGVsbG8="),
                                Plain("after"),
                            ],
                        )
                    ]
                )
            ]
        )
    )
    assert [part.kind for part in envelope.content] == [
        ContentKind.TEXT,
        ContentKind.TEXT,
        ContentKind.IMAGE,
        ContentKind.TEXT,
    ]
    assert envelope.content[0].value == "[Alice]\n"
    assert envelope.content[0].sender is not None
    assert envelope.content[0].sender.name == "Alice"
    assert envelope.content[-1].value == "after"


def test_projection_bounds_forward_nesting_and_component_count():
    from astrbot.core.message.components import Forward, Plain
    from astrbot.core.platform.message_projection import envelope_from_event

    nested = Plain("leaf")
    for _ in range(9):
        nested = Forward(id="forward", content=[nested])

    envelope = envelope_from_event(_event(components=[nested]))

    from astrbot.core.platform.message_i18n import message_key

    assert envelope.content[-1] == PortablePart(
        ContentKind.TEXT, message_key("forward_limit")
    )
    assert (
        plan_delivery(envelope, MessageDeliveryCapabilities())[0].parts[0].value
        == "[转发嵌套上限]"
    )
    assert (
        plan_delivery(envelope, MessageDeliveryCapabilities(), locale="en-US")[0]
        .parts[0]
        .value
        == "[Forward nesting limit]"
    )


def test_envelope_from_event_records_bot_account_id():
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(_event())
    assert envelope.metadata["bot_account_id"] == "bot"


def test_projection_unknown_component_keeps_native_payload_and_safe_fallback():
    from astrbot.core.message.components import Poke
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(_event(components=[Poke(id="42")]))

    assert len(envelope.content) == 1
    native = envelope.content[0]
    assert isinstance(native, NativeContent)
    assert native.namespace == "telegram"
    assert native.kind == "poke"
    assert native.fallback == "[Poke]"


def test_delivery_planner_drops_unrepresentable_content_without_empty_batches():
    envelope = MessageEnvelope(
        _route(),
        content=(PortablePart(ContentKind.LOCATION, {"lat": 1, "lon": 2}),),
    )

    assert plan_delivery(envelope, MessageDeliveryCapabilities(text=False)) == ()


def test_native_snapshot_is_detached_and_encoder_rehydrates_each_send():
    from astrbot.core.message.components import Json
    from astrbot.core.platform.message_projection import envelope_from_event

    component = Json(data={"key": "original"})
    event = _event(components=[component])
    event.get_platform_name = lambda: "lark"
    envelope = envelope_from_event(event)
    component.data["key"] = "changed"
    capabilities = MessageDeliveryCapabilities(
        native_namespaces=frozenset({"lark"}), native_kinds=frozenset({"json"})
    )
    chain = plan_message_delivery(
        envelope, capabilities, target_umo=event.unified_msg_origin
    )[0]
    assert chain.chain[0].data == {"key": "original"}
    chain.chain[0].data["key"] = "mutated"
    assert plan_message_delivery(
        envelope, capabilities, target_umo=event.unified_msg_origin
    )[0].chain[0].data == {"key": "original"}


@pytest.mark.asyncio
async def test_unwatch_cancels_a_queued_delivery():
    import asyncio

    manager, authorization, send = _manager()
    event = _event()
    await manager.watch(event, "target:GroupMessage:room")
    checked = asyncio.Event()

    async def authorize(*args):
        if args[2].umo == "target:GroupMessage:room":
            checked.set()
        return SimpleNamespace(allowed=True)

    authorization.authorize.side_effect = authorize
    async with manager._delivery_locks.acquire_lock("source:FriendMessage:sender"):
        task = asyncio.create_task(
            manager.observe(
                MessageEnvelope(
                    PlatformRouteIdentity("target", MessageType.GROUP_MESSAGE, "room"),
                    content=(PortablePart(ContentKind.TEXT, "secret"),),
                )
            )
        )
        await checked.wait()
        assert await manager.unwatch(event, "target:GroupMessage:room")
    task_result = await task
    assert task_result is None
    send.assert_not_awaited()
    await manager.terminate()


@pytest.mark.asyncio
async def test_slow_destination_does_not_block_other_destination(tmp_path):
    import asyncio

    from astrbot.core.message.components import Image, Plain

    manager, _, _ = _manager()
    media = tmp_path / "image.png"
    media.write_bytes(b"image")
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_resolve():
        started.set()
        await release.wait()
        return str(media)

    image = Image()
    image.set_source_resolver(slow_resolve)
    slow = _event(
        components=[Plain("/send target:GroupMessage:x "), image],
    )
    fast = _event(components=[Plain("/send target:GroupMessage:y hello")])

    slow_task = asyncio.create_task(manager.send(slow, "target:GroupMessage:x"))
    await asyncio.wait_for(started.wait(), 1)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(slow_task), 0.05)

    receipt = await asyncio.wait_for(manager.send(fast, "target:GroupMessage:y"), 1)
    assert receipt.status == "accepted"

    release.set()
    await slow_task
    await manager.terminate()


@pytest.mark.asyncio
async def test_same_destination_deliveries_keep_arrival_order():
    import asyncio

    from astrbot.core.message.components import Plain

    events: list[str] = []
    first_started = asyncio.Event()
    release = asyncio.Event()

    async def send(_session, chain):
        text = chain.get_plain_text()
        events.append(f"start:{text}")
        if text == "first":
            first_started.set()
            await release.wait()
        events.append(f"end:{text}")
        return PlatformSendResult("target", True, "target", message_ids=("sent",))

    manager, _, _ = _manager(AsyncMock(side_effect=send))
    first = _event(components=[Plain("/send target:GroupMessage:room first")])
    second = _event(components=[Plain("/send target:GroupMessage:room second")])

    first_task = asyncio.create_task(manager.send(first, "target:GroupMessage:room"))
    await asyncio.wait_for(first_started.wait(), 1)
    second_task = asyncio.create_task(manager.send(second, "target:GroupMessage:room"))
    await asyncio.sleep(0)
    assert events == ["start:first"]

    release.set()
    await asyncio.gather(first_task, second_task)
    assert events == [
        "start:first",
        "end:first",
        "start:second",
        "end:second",
    ]
    await manager.terminate()


@pytest.mark.asyncio
async def test_observe_delivers_to_watches_without_head_of_line_blocking():
    import asyncio

    manager, _, sender = _manager()
    await manager.watch(_event(umo="x:FriendMessage:one"), "origin:GroupMessage:room")
    await manager.watch(_event(umo="y:FriendMessage:one"), "origin:GroupMessage:room")

    release = asyncio.Event()
    y_delivered = asyncio.Event()

    async def send(session, _chain):
        if session.platform_id == "x":
            await release.wait()
        if session.platform_id == "y":
            y_delivered.set()
        return PlatformSendResult(
            session.platform_id, True, session.session_id, message_ids=("sent",)
        )

    sender.side_effect = send
    task = asyncio.create_task(
        manager.observe(
            MessageEnvelope(
                PlatformRouteIdentity("origin", MessageType.GROUP_MESSAGE, "room"),
                content=(PortablePart(ContentKind.TEXT, "hello"),),
            )
        )
    )
    await asyncio.wait_for(y_delivered.wait(), 1)
    release.set()
    await task
    await manager.terminate()


@pytest.mark.asyncio
async def test_own_bot_echo_is_not_forwarded():
    manager, _, send = _manager()
    await manager.watch(_event(), "target:GroupMessage:room")
    await manager.observe(
        MessageEnvelope(
            PlatformRouteIdentity("target", MessageType.GROUP_MESSAGE, "room"),
            content=(PortablePart(ContentKind.TEXT, "echo"),),
            is_self_message=True,
        )
    )
    send.assert_not_awaited()
    await manager.terminate()


@pytest.mark.asyncio
async def test_cancelled_media_download_removes_partial_file(tmp_path, monkeypatch):
    import asyncio
    from pathlib import Path

    from astrbot.core.utils import media_utils

    target = tmp_path / "partial.bin"
    monkeypatch.setattr(media_utils, "_temp_media_path", lambda *_: target)

    async def download(_url, path):
        Path(path).write_bytes(b"partial")
        raise asyncio.CancelledError

    monkeypatch.setattr(media_utils, "download_file", download)
    with pytest.raises(asyncio.CancelledError):
        async with media_utils.MediaResolver("https://example.com/media").as_path():
            pytest.fail("Cancelled media must never be yielded")
    assert not target.exists()


@pytest.mark.parametrize(
    "module_name,class_name,platform_name",
    [
        (
            "qqofficial.qqofficial_platform_adapter",
            "QQOfficialPlatformAdapter",
            "qq_official",
        ),
        (
            "qqofficial_webhook.qo_webhook_adapter",
            "QQOfficialWebhookPlatformAdapter",
            "qq_official_webhook",
        ),
    ],
)
def test_qq_capabilities_use_runtime_name_and_target_session_state(
    module_name, class_name, platform_name
):
    from importlib import import_module

    from astrbot.core.platform.message_session import MessageSession

    adapter_type = getattr(
        import_module(f"astrbot.core.platform.sources.{module_name}"), class_name
    )
    adapter = object.__new__(adapter_type)
    adapter.meta = lambda: SimpleNamespace(name=platform_name)
    adapter._session_scene = {}
    adapter._session_last_message_id = {}
    adapter._allow_group_proactive_send = False
    session = MessageSession.from_str("qq:GroupMessage:room")
    assert not adapter.message_capabilities(session).proactive
    adapter._session_last_message_id["room"] = "id"
    assert adapter.message_capabilities(session).media == frozenset({"image"})
    adapter._session_scene["room"] = "group"
    assert adapter.message_capabilities(session).media == frozenset(
        {"image", "audio", "video", "file"}
    )


def test_media_capabilities_follow_wecom_mode_webhook_and_misskey_settings():
    from astrbot.core.platform.sources.misskey.misskey_adapter import (
        MisskeyPlatformAdapter,
    )
    from astrbot.core.platform.sources.wecom.wecom_adapter import WecomPlatformAdapter
    from astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter import (
        WecomAIBotAdapter,
    )

    wecom = object.__new__(WecomPlatformAdapter)
    wecom.meta = lambda: SimpleNamespace(name="wecom")
    wecom.client = SimpleNamespace(kf_message=True)
    wecom.agent_id = "agent"
    assert not wecom.message_capabilities().proactive
    wecom.client = SimpleNamespace()
    assert wecom.message_capabilities().proactive
    webhook = object.__new__(WecomAIBotAdapter)
    webhook.meta = lambda: SimpleNamespace(name="wecom_ai_bot")
    webhook.webhook_client = None
    assert not webhook.message_capabilities().proactive
    webhook.webhook_client = object()
    assert webhook.message_capabilities().proactive
    misskey = object.__new__(MisskeyPlatformAdapter)
    misskey.meta = lambda: SimpleNamespace(name="misskey")
    misskey.api = object()
    misskey.enable_file_upload = False
    misskey.max_message_length = 321
    assert not misskey.message_capabilities().media
    assert misskey.message_capabilities().max_text_length == 321
    misskey.max_message_length = "invalid"
    assert misskey.message_capabilities().max_text_length == 3000


def test_parse_watch_spec_accepts_this_omission_and_duration():
    from astrbot.builtin_stars.builtin_commands.commands.session import (
        parse_unwatch_spec,
        parse_watch_spec,
        parse_watches_spec,
    )

    current = "here:FriendMessage:me"
    assert parse_watch_spec("there:GroupMessage:room", current) == (
        current,
        "there:GroupMessage:room",
        None,
    )
    assert parse_watch_spec("this there:GroupMessage:room", current) == (
        current,
        "there:GroupMessage:room",
        None,
    )
    assert parse_watch_spec("there:GroupMessage:room 120", current) == (
        current,
        "there:GroupMessage:room",
        120,
    )
    assert parse_watch_spec(
        "other:FriendMessage:x there:GroupMessage:room 90", current
    ) == ("other:FriendMessage:x", "there:GroupMessage:room", 90)
    assert parse_unwatch_spec("there:GroupMessage:room", current) == (
        current,
        "there:GroupMessage:room",
    )
    assert parse_unwatch_spec("this there:GroupMessage:room", current) == (
        current,
        "there:GroupMessage:room",
    )
    assert parse_watches_spec("", current) == current
    assert parse_watches_spec("this", current) == current
    assert parse_watches_spec("other:FriendMessage:x", current) == (
        "other:FriendMessage:x"
    )


def test_is_umo_accepts_session_strings():
    from astrbot.builtin_stars.builtin_commands.commands.session import _is_umo

    assert _is_umo("target:GroupMessage:room")
    assert not _is_umo("hello")
    assert not _is_umo("")


def test_send_projection_strips_command_only_when_target_not_in_header():
    from astrbot.core.message.components import Plain
    from astrbot.core.platform.message_projection import envelope_from_send_event

    event = _event(components=[Plain("/send hello there")])
    envelope = envelope_from_send_event(
        event, "target:GroupMessage:room", target_in_header=False
    )
    assert [
        part.value for part in envelope.content if part.kind == ContentKind.TEXT
    ] == ["hello there"]
    with pytest.raises(ValueError):
        envelope_from_send_event(event, "target:GroupMessage:room")


@pytest.mark.asyncio
async def test_session_commands_connect_and_linked_send():
    from astrbot.builtin_stars.builtin_commands.commands.session import SessionCommands

    replies: list[str] = []
    link = SimpleNamespace(target_umo="target:GroupMessage:room", expires_at=None)

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    context = SimpleNamespace(
        bridges=SimpleNamespace(
            connect=AsyncMock(return_value=link),
            connection=AsyncMock(return_value=link),
            disconnect=AsyncMock(return_value=True),
            send=AsyncMock(return_value=SimpleNamespace(status="accepted")),
        ),
        i18n=SimpleNamespace(t=translate),
    )
    event = _event()
    event.set_result = lambda _result: None
    commands = SessionCommands(context)
    await commands.connect(event, "")
    await commands.connect(event, "target:GroupMessage:room")
    await commands.disconnect(event)
    await commands.send(event, "")
    await commands.send(event, "target:GroupMessage:room hello")
    assert replies == [
        "session.connect.status",
        "session.connect.ok",
        "session.disconnect.ok",
        "session.send.accepted",
        "session.send.accepted",
    ]
    context.bridges.send.assert_any_await(
        event, "target:GroupMessage:room", target_in_header=False
    )
    context.bridges.send.assert_any_await(
        event, "target:GroupMessage:room", target_in_header=True
    )


@pytest.mark.asyncio
async def test_session_commands_report_denied_without_actor():
    from astrbot.builtin_stars.builtin_commands.commands.session import SessionCommands

    replies: list[str] = []

    async def translate(_event, key, **_kwargs):
        replies.append(key)
        return key

    context = SimpleNamespace(
        bridges=SimpleNamespace(
            unwatch=AsyncMock(side_effect=PermissionError("denied")),
            list=AsyncMock(side_effect=PermissionError("denied")),
            connect=AsyncMock(side_effect=PermissionError("denied")),
            disconnect=AsyncMock(side_effect=PermissionError("denied")),
            connection=AsyncMock(side_effect=PermissionError("denied")),
        ),
        i18n=SimpleNamespace(t=translate),
    )
    event = _event()
    event.set_result = lambda _result: None
    commands = SessionCommands(context)
    await commands.unwatch(event, "target:GroupMessage:room")
    await commands.watches(event)
    await commands.connect(event, "target:GroupMessage:room")
    await commands.disconnect(event)
    assert replies == [
        "session.bridge.denied",
        "session.bridge.denied",
        "session.bridge.denied",
        "session.bridge.denied",
    ]


def _forward_nodes(chains):
    from astrbot.core.message.components import Nodes

    found = []
    for chain in chains:
        for component in chain.chain:
            if isinstance(component, Nodes):
                found.append(component)
    return found


def _napcat_event(components):
    event = _event(components=components)
    event.get_platform_name = lambda: "napcat"
    return event


def test_projection_stamps_sender_on_native_forward_parts():
    from astrbot.core.message.components import Face, Json, MFace, Node, Nodes, Plain
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(
                            name="Alice",
                            uin="1001",
                            content=[
                                Face(id=111),
                                MFace(
                                    emoji_package_id=1,
                                    emoji_id="eid",
                                    key="key",
                                    summary="s",
                                ),
                                Json(data={"app": "x"}),
                                Plain("hi"),
                            ],
                        )
                    ]
                )
            ]
        )
    )
    natives = [item for item in envelope.content if isinstance(item, NativeContent)]
    assert {item.kind for item in natives} == {"face", "mface", "json"}
    assert all(
        item.sender is not None and item.sender.name == "Alice" for item in natives
    )


def test_plan_message_delivery_reconstructs_nodes_when_target_supports_forward():
    from astrbot.core.message.components import Node, Nodes, Plain
    from astrbot.core.platform.message_projection import envelope_from_event
    from astrbot.core.platform.message_renderers import render_source_header

    envelope = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(name="Alice", uin="1001", content=[Plain("one")]),
                        Node(name="Alice", uin="1001", content=[Plain("two")]),
                        Node(name="Bob", uin="1002", content=[Plain("three")]),
                    ]
                )
            ]
        )
    )
    header = PortablePart(
        ContentKind.TEXT,
        render_source_header(envelope, "napcat"),
    )
    chains = plan_message_delivery(
        replace_content(envelope, (header, *envelope.content)),
        MESSAGE_CAPABILITIES["napcat"],
        target_umo="napcat:GroupMessage:room",
    )
    nodes = _forward_nodes(chains)
    assert len(nodes) == 1
    assert [(node.name, node.uin) for node in nodes[0].nodes] == [
        ("Alice", "1001"),
        ("Alice", "1001"),
        ("Bob", "1002"),
    ]
    bodies = [
        "".join(part.text for part in node.content if isinstance(part, Plain))
        for node in nodes[0].nodes
    ]
    assert bodies == ["one", "two", "three"]
    header_text = chains[0].get_plain_text()
    assert "来自" in header_text
    assert all("[Alice]\n" not in body and "[Bob]\n" not in body for body in bodies)


def replace_content(envelope, content):
    from dataclasses import replace

    return replace(envelope, content=tuple(content))


def test_plan_message_delivery_splits_sender_islands():
    from astrbot.core.message.components import Node, Nodes, Plain
    from astrbot.core.platform.message_projection import envelope_from_event

    forwarded = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(name="Alice", uin="1001", content=[Plain("first")]),
                        Node(name="Bob", uin="1002", content=[Plain("second")]),
                    ]
                )
            ]
        )
    )
    middle = PortablePart(ContentKind.TEXT, "between")
    envelope = replace_content(
        forwarded, (*forwarded.content[:2], middle, *forwarded.content[2:])
    )
    chains = plan_message_delivery(
        envelope,
        MESSAGE_CAPABILITIES["napcat"],
        target_umo="napcat:GroupMessage:room",
    )
    nodes = _forward_nodes(chains)
    assert len(nodes) == 2
    assert [chain.get_plain_text() for chain in chains if chain.get_plain_text()] == [
        "between"
    ]
    assert nodes[0].nodes[0].name == "Alice"
    assert nodes[1].nodes[0].name == "Bob"


def test_plan_message_delivery_strips_unknown_author_separator():
    from astrbot.core.message.components import Node, Nodes, Plain
    from astrbot.core.platform.message_i18n import message_key
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(
        _napcat_event([Nodes(nodes=[Node(name="", uin="", content=[Plain("hi")])])])
    )
    assert envelope.content[0].value == message_key("unknown_author")
    chains = plan_message_delivery(
        envelope,
        MESSAGE_CAPABILITIES["napcat"],
        target_umo="napcat:GroupMessage:room",
        locale="zh-CN",
    )
    node = _forward_nodes(chains)[0].nodes[0]
    assert node.name == "未知"
    assert node.uin == "0"
    texts = [part.text for part in node.content if isinstance(part, Plain)]
    assert texts == ["hi"]
    assert all("[未知]\n" not in text for text in texts)


def test_plan_message_delivery_does_not_wrap_ordinary_messages():
    chains = plan_message_delivery(
        MessageEnvelope(_route(), content=(PortablePart(ContentKind.TEXT, "hello"),)),
        MESSAGE_CAPABILITIES["napcat"],
        target_umo="napcat:GroupMessage:room",
    )
    assert _forward_nodes(chains) == []
    assert chains[0].get_plain_text() == "hello"


def test_plan_message_delivery_keeps_qq_node_segments():
    from astrbot.core.message.components import (
        RPS,
        Contact,
        Dice,
        Face,
        Json,
        Location,
        Markdown,
        Mention,
        MentionAll,
        MFace,
        MiniApp,
        Music,
        Node,
        Nodes,
        Plain,
        Poke,
        Shake,
        Share,
        Xml,
    )
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(
                            name="Alice",
                            uin="1001",
                            content=[
                                Face(id=111),
                                MFace(
                                    emoji_package_id=1,
                                    emoji_id="eid",
                                    key="key",
                                    summary="wow",
                                ),
                                Json(data={"app": "x"}),
                                Poke(id="42"),
                                Markdown("md"),
                                MiniApp(data="mini"),
                                Xml(data="<xml/>"),
                                Dice(),
                                RPS(),
                                Shake(),
                                Share(url="https://example.com", title="t"),
                                Music(_type="qq", id=1),
                                Location(lat=1.5, lon=2.5, title="park"),
                                Contact(_type="qq", id=99),
                                Mention(target="7", name="Bob"),
                                MentionAll(),
                                Plain("end"),
                            ],
                        )
                    ]
                )
            ]
        )
    )
    chains = plan_message_delivery(
        envelope,
        MESSAGE_CAPABILITIES["napcat"],
        target_umo="napcat:GroupMessage:room",
    )
    content = _forward_nodes(chains)[0].nodes[0].content
    types = [type(part) for part in content]
    assert types[:12] == [
        Face,
        MFace,
        Json,
        Poke,
        Markdown,
        MiniApp,
        Xml,
        Dice,
        RPS,
        Shake,
        Share,
        Music,
    ]
    assert isinstance(content[12], Location)
    assert content[12].lat == 1.5
    assert content[12].lon == 2.5
    assert content[12].title == "park"
    assert content[12].content == ""
    assert isinstance(content[13], Contact)
    assert content[13].sub_type == "qq"
    assert [part.text for part in content if isinstance(part, Plain)] == [
        "@Bob",
        "@all",
        "end",
    ]


def test_plan_message_delivery_contact_uses_sub_type():
    from astrbot.core.message.components import Contact, Node, Nodes
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(
                            name="Alice",
                            uin="1001",
                            content=[Contact(_type="group", id=8)],
                        )
                    ]
                )
            ]
        )
    )
    contact = (
        _forward_nodes(
            plan_message_delivery(
                envelope,
                MESSAGE_CAPABILITIES["napcat"],
                target_umo="napcat:GroupMessage:room",
            )
        )[0]
        .nodes[0]
        .content[0]
    )
    assert isinstance(contact, Contact)
    assert contact.sub_type == "group"


def test_plan_message_delivery_omits_invalid_location_and_contact():
    from astrbot.core.message.components import Location, Node, Nodes, Plain
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(
                            name="Alice",
                            uin="1001",
                            content=[
                                Location(lat=1.5, lon=2.5, title="park"),
                                Plain("kept"),
                            ],
                        )
                    ]
                )
            ]
        )
    )
    broken = replace_content(
        envelope,
        (
            envelope.content[0],
            PortablePart(
                ContentKind.LOCATION,
                {"lat": None, "lon": 2},
                sender=envelope.content[1].sender,
            ),
            PortablePart(
                ContentKind.CONTACT,
                {"type": "qq", "id": "not-a-number"},
                sender=envelope.content[1].sender,
            ),
            envelope.content[1],
            envelope.content[2],
        ),
    )
    content = (
        _forward_nodes(
            plan_message_delivery(
                broken,
                MESSAGE_CAPABILITIES["napcat"],
                target_umo="napcat:GroupMessage:room",
            )
        )[0]
        .nodes[0]
        .content
    )
    assert [type(part) for part in content] == [Location, Plain]
    assert content[0].lat == 1.5
    assert [part.text for part in content if isinstance(part, Plain)] == ["kept"]


def test_plan_message_delivery_contact_coerces_string_id():
    from astrbot.core.message.components import Contact

    sender = SenderSnapshot("1001", "Alice", "napcat")
    envelope = MessageEnvelope(
        _route(),
        content=(
            PortablePart(ContentKind.TEXT, "[Alice]\n", sender=sender),
            PortablePart(
                ContentKind.CONTACT, {"type": "qq", "id": "99"}, sender=sender
            ),
        ),
    )
    contact = (
        _forward_nodes(
            plan_message_delivery(
                envelope,
                MESSAGE_CAPABILITIES["napcat"],
                target_umo="napcat:GroupMessage:room",
            )
        )[0]
        .nodes[0]
        .content[0]
    )
    assert isinstance(contact, Contact)
    assert contact.sub_type == "qq"
    assert contact.id == 99


def test_plan_message_delivery_cross_platform_id_replays_node_faces():
    from astrbot.core.message.components import Face, Json, MFace, Node, Nodes
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(
                            name="Alice",
                            uin="1001",
                            content=[
                                Face(id=111),
                                MFace(
                                    emoji_package_id=1,
                                    emoji_id="eid",
                                    key="key",
                                    summary="s",
                                ),
                                Json(data={"app": "x"}),
                            ],
                        )
                    ]
                )
            ]
        )
    )
    content = (
        _forward_nodes(
            plan_message_delivery(
                envelope,
                MESSAGE_CAPABILITIES["napcat"],
                target_umo="other-napcat:GroupMessage:room",
            )
        )[0]
        .nodes[0]
        .content
    )
    assert [type(part) for part in content] == [Face, MFace, Json]


def test_plan_message_delivery_does_not_emit_root_level_poke():
    from astrbot.core.message.components import Poke
    from astrbot.core.platform.message_projection import envelope_from_event

    envelope = envelope_from_event(_napcat_event([Poke(id="42")]))
    chains = plan_message_delivery(
        envelope,
        MESSAGE_CAPABILITIES["napcat"],
        target_umo="napcat:GroupMessage:room",
    )
    assert _forward_nodes(chains) == []
    assert all(not isinstance(part, Poke) for chain in chains for part in chain.chain)
    assert "[Poke]" in chains[0].get_plain_text()


def test_plan_message_delivery_flattens_native_summaries_when_forward_false():
    from astrbot.core.message.components import Face, Json, MFace, Node, Nodes, Plain
    from astrbot.core.message.json_card import format_json_card_prompt
    from astrbot.core.message.qq_face import format_qq_face
    from astrbot.core.platform.message_projection import envelope_from_event

    json_card = Json(data={"app": "com.example.unknown"})
    envelope = envelope_from_event(
        _napcat_event(
            [
                Nodes(
                    nodes=[
                        Node(
                            name="Alice",
                            uin="1001",
                            content=[
                                Face(id=111),
                                MFace(
                                    emoji_package_id=1,
                                    emoji_id="eid",
                                    key="key",
                                    summary="wow",
                                ),
                                json_card,
                                Plain("hi"),
                            ],
                        )
                    ]
                )
            ]
        )
    )
    chains = plan_message_delivery(
        envelope,
        MessageDeliveryCapabilities(),
        target_umo="telegram:FriendMessage:1",
    )
    assert _forward_nodes(chains) == []
    text = chains[0].get_plain_text()
    assert text.startswith("[Alice]\n")
    assert format_qq_face(111) in text
    assert "wow" in text
    assert format_json_card_prompt(json_card) in text
