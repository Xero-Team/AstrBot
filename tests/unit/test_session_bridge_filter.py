import re

import pytest

from astrbot.core.auth.models import Role
from astrbot.core.platform.message_protocol import (
    ContentKind,
    MediaReference,
    NativeContent,
    PortablePart,
)
from astrbot.core.platform.session_bridge_filter import (
    append_filter_value,
    compile_text_pattern,
    evaluate_filter,
    portable_text,
    validate_filter_value,
)


def test_empty_filter_forwards():
    assert evaluate_filter(
        {},
        {},
        subject_id="im:target:bot:1",
        has_sender=True,
        role=Role.MEMBER.value,
        text="hello",
    )


def test_match_and_except_subjects_roles_and_text():
    assert evaluate_filter(
        {"subjects": ["im:target:bot:1"], "roles": ["member"], "text": ["hello"]},
        {},
        subject_id="im:target:bot:1",
        has_sender=True,
        role=Role.MEMBER.value,
        text="hello world",
    )
    assert not evaluate_filter(
        {"subjects": ["im:target:bot:1"], "roles": ["member"], "text": ["hello"]},
        {},
        subject_id="im:target:bot:1",
        has_sender=True,
        role=Role.GUEST.value,
        text="hello world",
    )
    assert not evaluate_filter(
        {"subjects": ["im:target:bot:1"]},
        {"subjects": ["im:target:bot:1"]},
        subject_id="im:target:bot:1",
        has_sender=True,
        role=Role.MEMBER.value,
        text="hello",
    )


def test_same_dimension_is_or():
    assert evaluate_filter(
        {"roles": ["member", "session_admin"]},
        {},
        subject_id="im:target:bot:1",
        has_sender=True,
        role=Role.SESSION_ADMIN.value,
        text="hello",
    )


def test_missing_sender_subject_rules():
    assert not evaluate_filter(
        {"subjects": ["im:target:bot:1"]},
        {},
        subject_id=None,
        has_sender=False,
        role=Role.GUEST.value,
        text="hello",
    )
    assert evaluate_filter(
        {},
        {"subjects": ["im:target:bot:1"]},
        subject_id=None,
        has_sender=False,
        role=Role.GUEST.value,
        text="hello",
    )


def test_pure_media_text_rules():
    assert (
        portable_text(
            (
                PortablePart(ContentKind.IMAGE, MediaReference("file:///x.jpg")),
                NativeContent("telegram", "sticker", "{}"),
            )
        )
        == ""
    )
    assert not evaluate_filter(
        {"text": ["hello"]},
        {},
        subject_id="im:target:bot:1",
        has_sender=True,
        role=Role.MEMBER.value,
        text="",
    )
    assert evaluate_filter(
        {},
        {"text": ["hello"]},
        subject_id="im:target:bot:1",
        has_sender=True,
        role=Role.MEMBER.value,
        text="",
    )


def test_portable_text_concatenates_string_parts_only():
    assert (
        portable_text(
            (
                PortablePart(ContentKind.TEXT, "a"),
                PortablePart(ContentKind.IMAGE, MediaReference("file:///x.jpg")),
                PortablePart(ContentKind.TEXT, "b"),
                NativeContent("telegram", "sticker", "{}", fallback="no"),
            )
        )
        == "ab"
    )


def test_compile_text_pattern_uses_stdlib_re():
    assert compile_text_pattern("hello").search("say hello")
    assert compile_text_pattern("(?i)hello").search("HELLO")
    assert compile_text_pattern("hello").search("HELLO") is None
    with pytest.raises(ValueError, match="Invalid filter pattern"):
        compile_text_pattern("(")
    with pytest.raises(ValueError, match="Invalid filter pattern"):
        compile_text_pattern("x" * 257)
    assert isinstance(compile_text_pattern("a"), re.Pattern)


def test_validate_and_append_limits():
    assert validate_filter_value("roles", "session_admin") == "session_admin"
    with pytest.raises(ValueError, match="Invalid filter role"):
        validate_filter_value("roles", "admin")
    current = {}
    for index in range(16):
        current = append_filter_value(current, "subjects", f"im:target:bot:{index}")
    current = append_filter_value(current, "subjects", "im:target:bot:0")
    with pytest.raises(ValueError, match="Filter limit exceeded"):
        append_filter_value(current, "subjects", "im:target:bot:16")
