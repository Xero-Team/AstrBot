import pytest

from astrbot.core.message.components import File, Forward, Mention, Node, Reply
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent


@pytest.mark.asyncio
async def test_satori_component_attributes_escape_untrusted_values(tmp_path):
    mention = await SatoriPlatformEvent._convert_component_to_satori_static(
        Mention(target='1" onmouseover="alert(1)')
    )
    named_mention = await SatoriPlatformEvent._convert_component_to_satori_static(
        Mention(target="", name='a&b"<c')
    )
    source = tmp_path / "a b&c.txt"
    source.write_text("payload", encoding="utf-8")
    file = await SatoriPlatformEvent._convert_component_to_satori_static(
        File(name='a"b<c', file=str(source))
    )
    reply = await SatoriPlatformEvent._convert_component_to_satori_static(
        Reply(id='1" onmouseover="alert(1)')
    )
    forward = await SatoriPlatformEvent._convert_component_to_satori_static(
        Forward(id='1" onmouseover="alert(1)')
    )

    for output in (mention, file, reply, forward):
        assert 'onmouseover="' not in output
        assert "&quot;" in output or "&amp;" in output or "&lt;" in output
    assert "a&amp;b&quot;&lt;c" in named_mention
    assert "a&quot;b&lt;c" in file
    assert "a b&amp;c.txt" in file


@pytest.mark.asyncio
async def test_satori_node_author_attributes_escape_untrusted_values():
    node = Node([], uin='u" onmouseover="alert(1)', name="n&<")

    result = await SatoriPlatformEvent._convert_node_to_satori_static(node)

    assert 'onmouseover="' not in result
    assert 'id="u&quot; onmouseover=&quot;alert(1)"' in result
    assert 'name="n&amp;&lt;"' in result
