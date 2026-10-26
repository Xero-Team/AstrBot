from astrbot.core.platform.contracts.onebot import OneBotFileResult
from astrbot.core.platform.sources.napcat.napcat_platform_adapter import (
    NapCatPlatformAdapter,
)

FILE_ACTIONS = (
    "get_image",
    "get_file",
    "get_group_file_url",
    "get_private_file_url",
)


def test_file_actions_unwrap_wrapped_response_data():
    for action in FILE_ACTIONS:
        result = NapCatPlatformAdapter._to_onebot_result(
            action,
            {
                "status": "ok",
                "retcode": 0,
                "data": {
                    "file_id": "file-1",
                    "url": "https://example.test/file",
                    "file": "name.txt",
                },
            },
        )

        assert isinstance(result, OneBotFileResult)
        assert result.file_id == "file-1"
        assert result.url == "https://example.test/file"
        assert result.file == "name.txt"
        assert result.payload["status"] == "ok"


def test_file_actions_accept_unwrapped_payloads():
    result = NapCatPlatformAdapter._to_onebot_result(
        "get_image",
        {"file_id": "file-2", "url": "https://example.test/image"},
    )

    assert isinstance(result, OneBotFileResult)
    assert result.file_id == "file-2"
    assert result.url == "https://example.test/image"
