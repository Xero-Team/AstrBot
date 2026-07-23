from pathlib import Path

import pytest

from astrbot.core.message.components import Record
from astrbot.core.webchat.message_parts import (
    parse_webchat_message_parts,
)


@pytest.mark.asyncio
async def test_parse_webchat_message_parts_keeps_record_path_without_eager_conversion(
    tmp_path: Path,
):
    record_path = tmp_path / "voice.amr"
    record_path.write_bytes(b"voice-bytes")

    components, text_parts, has_content = await parse_webchat_message_parts(
        [{"type": "record", "path": str(record_path)}],
    )

    assert text_parts == []
    assert has_content is True
    assert len(components) == 1
    assert isinstance(components[0], Record)
    assert components[0].file == str(record_path.resolve())
    assert components[0].url == str(record_path.resolve())
