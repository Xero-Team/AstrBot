from types import SimpleNamespace
from typing import Annotated

import pytest

from astrbot.core.star.filter.command import CommandFilter, GreedyStr, option
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata
from astrbot.core.utils.command_parser import CommandParseError, tokenize_command_args


class DummyEvent:
    def __init__(self, message_str: str, *, at_or_wake: bool = True) -> None:
        self.message_str = message_str
        self.is_at_or_wake_command = at_or_wake
        self._extras: dict[str, object] = {}

    def get_message_str(self) -> str:
        return self.message_str

    def set_extra(self, key: str, value: object) -> None:
        self._extras[key] = value

    def get_extra(self, key: str, default=None):
        return self._extras.get(key, default)


def _handler_metadata(handler) -> StarHandlerMetadata:
    return StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{handler.__module__}_{handler.__name__}",
        handler_name=handler.__name__,
        handler_module_path=handler.__module__,
        handler=handler,
        event_filters=[],
    )


def _dummy_config():
    return SimpleNamespace()


def test_tokenize_command_args_supports_quotes_and_adjacent_segments() -> None:
    tokens = tokenize_command_args('alpha "beta gamma" delta"42"')

    assert tokens == ["alpha", "beta gamma", "delta42"]


def test_tokenize_command_args_supports_escapes_without_breaking_windows_paths() -> (
    None
):
    tokens = tokenize_command_args(r'"C:\Users\bot" escaped\ value say\"hi\" tail\\')

    assert tokens == [r"C:\Users\bot", "escaped value", 'say"hi"', "tail\\"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('"unterminated', "未闭合的双引号"),
        ("'unterminated", "未闭合的单引号"),
        ("unfinished\\", "反斜杠转义未完成"),
    ],
)
def test_tokenize_command_args_reports_precise_errors(
    message: str, expected: str
) -> None:
    with pytest.raises(CommandParseError, match=expected):
        tokenize_command_args(message)


def test_command_filter_parses_quoted_and_typed_arguments() -> None:
    async def handler(self, event, title: str, count: int) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent('demo "hello world" 3')

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"title": "hello world", "count": 3}


def test_command_filter_keeps_greedy_string_after_tokenization() -> None:
    async def handler(self, event, alias: GreedyStr) -> None: ...

    command = CommandFilter("name")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent('name "Alice Bob" senior')

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"alias": "Alice Bob senior"}


def test_command_group_filter_rejects_similar_prefixes() -> None:
    group = CommandGroupFilter("plugin")
    event = DummyEvent("pluginx on")

    assert group.filter(event, _dummy_config()) is False


def test_command_group_filter_accepts_extra_spacing_between_segments() -> None:
    group = CommandGroupFilter("plugin")
    event = DummyEvent("plugin   on demo")

    assert group.filter(event, _dummy_config()) is True


def test_command_filter_supports_bool_flag_option() -> None:
    async def handler(
        self,
        event,
        name: str,
        force: Annotated[bool, option("--force", "-f")] = False,
    ) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo alice --force")

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"name": "alice", "force": True}


def test_command_filter_supports_value_option_before_positionals() -> None:
    async def handler(
        self,
        event,
        name: str,
        page: Annotated[int | None, option("--page", "-p")] = None,
    ) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo --page=2 alice")

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"name": "alice", "page": 2}


def test_command_filter_keeps_unknown_option_like_tokens_as_positionals() -> None:
    async def handler(self, event, raw: str) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo --raw-token")

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"raw": "--raw-token"}


def test_command_filter_reports_missing_option_value() -> None:
    async def handler(
        self,
        event,
        name: str,
        page: Annotated[int | None, option("--page", "-p")] = None,
    ) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo alice --page")

    with pytest.raises(ValueError, match="选项 --page 缺少值"):
        command.filter(event, _dummy_config())


def test_command_filter_supports_explicit_bool_option_value() -> None:
    async def handler(
        self,
        event,
        name: str,
        force: Annotated[bool, option("--force", "-f")] = False,
    ) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo alice --force=false")

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"name": "alice", "force": False}


def test_command_filter_supports_space_separated_bool_option_value() -> None:
    async def handler(
        self,
        event,
        name: str,
        force: Annotated[bool, option("--force", "-f")] = False,
    ) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo alice --force false")

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"name": "alice", "force": False}


def test_command_filter_supports_option_terminator_for_dash_prefixed_values() -> (
    None
):
    async def handler(
        self,
        event,
        name: str,
        force: Annotated[bool, option("--force", "-f")] = False,
    ) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo -- --force")

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"name": "--force", "force": False}


def test_command_filter_stops_parsing_options_after_terminator() -> None:
    async def handler(
        self,
        event,
        name: str,
        page: Annotated[int | None, option("--page", "-p")] = None,
    ) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo --page=2 -- --page")

    assert command.filter(event, _dummy_config()) is True
    assert event.get_extra("parsed_params") == {"name": "--page", "page": 2}


def test_command_filter_reports_unexpected_extra_positionals() -> None:
    async def handler(self, event, name: str) -> None: ...

    command = CommandFilter("demo")
    command.init_handler_md(_handler_metadata(handler))
    event = DummyEvent("demo alice bob")

    with pytest.raises(ValueError, match="参数过多"):
        command.filter(event, _dummy_config())
