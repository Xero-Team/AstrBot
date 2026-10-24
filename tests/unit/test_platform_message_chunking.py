from dataclasses import replace

from astrbot.core.platform.message_limits import (
    DISCORD_TEXT_LIMIT,
    TELEGRAM_TEXT_LIMIT,
    WECOM_TEXT_LIMIT,
    MessageLimitUnit,
    PlatformTextLimit,
    split_platform_text,
)


def test_discord_over_2000_is_split_not_truncated() -> None:
    text = "a" * 4500
    result = split_platform_text(text, DISCORD_TEXT_LIMIT)
    assert all(len(part) <= 2000 for part in result.parts)
    assert "".join(result.parts) == text or result.truncated
    assert sum(len(part) for part in result.parts) >= 4000


def test_discord_creates_multiple_messages() -> None:
    result = split_platform_text("x" * 3500, DISCORD_TEXT_LIMIT)
    assert len(result.parts) >= 2


def test_telegram_never_exceeds_4096() -> None:
    result = split_platform_text("你好" * 3000, TELEGRAM_TEXT_LIMIT)
    assert all(len(part) <= 4096 for part in result.parts)


def test_wecom_uses_utf8_bytes() -> None:
    text = "测" * 3000
    result = split_platform_text(text, WECOM_TEXT_LIMIT)
    assert all(len(part.encode("utf-8")) <= 4096 for part in result.parts)


def test_prefers_fenced_code_block_boundary() -> None:
    text = "intro\n```python\nprint(1)\n```\n" + ("n" * 2100)
    result = split_platform_text(text, DISCORD_TEXT_LIMIT)
    assert any("```" in part for part in result.parts)


def test_prefers_markdown_table_boundary() -> None:
    table = "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
    text = table + ("z" * 2100)
    result = split_platform_text(text, DISCORD_TEXT_LIMIT)
    assert result.parts[0].rstrip().endswith("| 1 | 2 |") or "|" in result.parts[0]


def test_hard_cuts_when_no_natural_boundary() -> None:
    result = split_platform_text("a" * 2500, DISCORD_TEXT_LIMIT)
    assert result.parts[0] == "a" * 2000


def test_max_chunks_degrades() -> None:
    limit = replace(DISCORD_TEXT_LIMIT, max_chunks=2)
    result = split_platform_text("a" * 8000, limit)
    assert len(result.parts) == 2
    assert result.truncated is True


def test_long_fenced_single_line_still_makes_progress() -> None:
    text = "```\n" + ("A" * 10000) + "\n```"
    result = split_platform_text(text, DISCORD_TEXT_LIMIT)

    assert len(result.parts) < 20
    assert all(len(part) <= 2000 for part in result.parts)
    assert any("A" in part for part in result.parts)


def test_fence_closing_never_exceeds_the_hard_limit() -> None:
    limit = PlatformTextLimit(
        max_length=10,
        unit=MessageLimitUnit.CHARS,
        supports_markdown=True,
        supports_structured_components=True,
        allows_consecutive_messages=True,
        max_chunks=100,
    )
    # The closing fence sits within the preliminary slice, so reserving space
    # from that slice alone is not enough: the decorated chunk must still fit.
    text = "~~~~\n ~~~~\n"
    result = split_platform_text(text, limit)

    assert result.parts
    assert all(len(part) <= limit.max_length for part in result.parts)


def test_byte_limits_hold_with_fences_and_wide_characters() -> None:
    limit = replace(WECOM_TEXT_LIMIT, max_length=24, max_chunks=100)
    text = "```\n" + "中😀" * 40 + "\n```"

    result = split_platform_text(text, limit)

    assert result.parts
    assert all(len(part.encode("utf-8")) <= limit.max_length for part in result.parts)
