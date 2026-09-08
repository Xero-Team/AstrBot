import hashlib

from astrbot.core.platform.sources.weixin_oc.weixin_oc_quote import (
    build_ilink_client_version,
    ref_message_id,
    resolve_partial_quote,
)


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


def test_build_ilink_client_version_encodes_major_minor_patch():
    assert build_ilink_client_version("1.0.11") == str(0x0001000B)
    assert build_ilink_client_version("4.28.0") == str((4 << 16) | (28 << 8))


def test_ref_message_id_prefers_svr_id():
    assert (
        ref_message_id({"svr_id": "svr-1", "message_item": {"msg_id": "item-1"}})
        == "svr-1"
    )
    assert ref_message_id({"message_item": {"msg_id": "item-1"}}) == "item-1"
    assert ref_message_id({}) == ""


def test_resolve_partial_quote_uses_global_occurrence_indexes():
    assert (
        resolve_partial_quote(
            "abcedfabcgh",
            {
                "start": "a",
                "end": "c",
                "startindex": 1,
                "endindex": 1,
                "quotemd5": _md5("abc"),
            },
        )
        == "abc"
    )


def test_resolve_partial_quote_uses_hash_for_relative_end_index():
    full = "x-end start first-end second-end"
    selected = "start first-end second-end"
    assert (
        resolve_partial_quote(
            full,
            {
                "start": "start",
                "end": "end",
                "startindex": 0,
                "endindex": 1,
                "quotemd5": _md5(selected),
            },
        )
        == selected
    )


def test_resolve_partial_quote_returns_none_for_invalid_or_mismatched_hash():
    assert (
        resolve_partial_quote(
            "hello",
            {
                "start": "h",
                "end": "o",
                "startindex": -1,
                "endindex": 0,
                "quotemd5": "",
            },
        )
        is None
    )
    assert (
        resolve_partial_quote(
            "hello",
            {
                "start": "h",
                "end": "o",
                "startindex": 0,
                "endindex": 0,
                "quotemd5": "not-the-md5",
            },
        )
        is None
    )
