from astrbot.core.platform.sources.aiocqhttp.forward_node_splitter import (
    split_long_text_node,
)


def test_split_long_text_node_prefers_sentence_boundaries_and_hard_limits():
    chunks = split_long_text_node("one。two。three", 5, r"[^。]+。")

    assert chunks == ["one。", "two。", "three"]
    assert all(len(chunk) <= 5 for chunk in chunks)


def test_split_long_text_node_uses_hard_limit_without_boundary():
    assert split_long_text_node("abcdefgh", 3, r"[^。]+。") == ["abc", "def", "gh"]
