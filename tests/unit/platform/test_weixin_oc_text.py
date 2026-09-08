from astrbot.core.platform.sources.weixin_oc.weixin_oc_text import (
    parse_tool_progress,
    split_plain_text,
)


def test_split_plain_text_keeps_short_text():
    assert split_plain_text("hello", 4000) == ["hello"]
    assert split_plain_text("", 4000) == []


def test_split_plain_text_prefers_punctuation_near_limit():
    text = ("甲" * 20) + "。" + ("乙" * 20)
    chunks = split_plain_text(text, 25)
    assert chunks[0].endswith("。")
    assert "".join(chunks) == text
    assert all(len(chunk) <= 25 for chunk in chunks)


def test_parse_tool_progress_start_and_result():
    start = parse_tool_progress("🔨 调用工具: web_search")
    assert start == {
        "phase": "start",
        "tool_name": "web_search",
        "status": "unknown",
    }
    result = parse_tool_progress("🔨 调用工具: web_search\n📎 返回结果: ok")
    assert result == {
        "phase": "end",
        "tool_name": "web_search",
        "status": "completed",
    }
