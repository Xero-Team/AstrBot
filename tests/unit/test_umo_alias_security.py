from typing import Any
from unicodedata import category

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astrbot.core.umo_alias import MAX_UMO_NAME_LENGTH, normalize_umo_name, parse_umo

PROPERTY_SETTINGS = settings(
    database=None,
    deadline=None,
    derandomize=True,
    max_examples=120,
)


_UMO_VALUES = st.one_of(
    st.none(),
    st.text(max_size=512),
    st.integers(),
    st.binary(max_size=64),
    st.lists(st.integers(), max_size=8),
    st.dictionaries(st.text(max_size=16), st.integers(), max_size=8),
)


@PROPERTY_SETTINGS
@given(_UMO_VALUES)
def test_parse_umo_has_a_stable_string_structure_for_arbitrary_input(
    value: Any,
) -> None:
    parsed = parse_umo(value)
    value_as_text = "" if value is None else str(value)
    parts = value_as_text.split(":")

    assert tuple(parsed) == ("platform", "message_type", "session_id")
    assert all(isinstance(item, str) for item in parsed.values())
    assert parsed == {
        "platform": parts[0] if parts[0] else "unknown",
        "message_type": parts[1] if len(parts) >= 2 and parts[1] else "unknown",
        "session_id": ":".join(parts[2:]) if len(parts) >= 3 else value_as_text,
    }
    assert parse_umo(value) == parsed


@PROPERTY_SETTINGS
@given(st.text(max_size=512))
def test_normalize_umo_name_removes_all_control_characters(name: str) -> None:
    normalized = normalize_umo_name(name)

    assert len(normalized) <= MAX_UMO_NAME_LENGTH
    assert all(category(character) != "Cc" for character in normalized)
    assert normalize_umo_name(normalized) == normalized


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("  工程🙂  ", "工程🙂"),
        ("\x00工程\t聊天室\r\n🙂\x7f", "工程 聊天室  🙂"),
        ("\u0085Alice\u009f", "Alice"),
    ],
)
def test_normalize_umo_name_preserves_unicode_without_control_characters(
    raw_name: str,
    expected: str,
) -> None:
    assert normalize_umo_name(raw_name) == expected
