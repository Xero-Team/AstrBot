import inspect
import types
import typing
from dataclasses import dataclass
from typing import Any

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.command_parser import tokenize_command_args

from ..star_handler import StarHandlerMetadata
from . import HandlerFilter
from .custom_filter import CustomFilter


class GreedyStr(str):
    """标记指令完成其他参数接收后的所有剩余文本。"""


@dataclass(frozen=True, slots=True)
class CommandOptionSpec:
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandParamSpec:
    name: str
    annotation: Any
    default: Any
    option: CommandOptionSpec | None = None

    @property
    def has_default(self) -> bool:
        return self.default is not inspect.Parameter.empty

    @property
    def is_greedy(self) -> bool:
        return self.annotation is GreedyStr

    @property
    def is_required(self) -> bool:
        return not self.has_default


def option(*option_names: str) -> CommandOptionSpec:
    """Declare optional command flags for `typing.Annotated` parameters."""

    if not option_names:
        raise ValueError("option 至少需要一个名称。")

    normalized_names: list[str] = []
    for option_name in option_names:
        if not option_name.startswith("-"):
            raise ValueError(f"option 名称必须以 '-' 开头: {option_name}")
        if option_name in normalized_names:
            raise ValueError(f"重复的 option 名称: {option_name}")
        normalized_names.append(option_name)

    return CommandOptionSpec(names=tuple(normalized_names))


def unwrap_optional(annotation) -> tuple:
    """去掉 Optional[T] / Union[T, None] / T|None，返回 T"""
    args = typing.get_args(annotation)
    non_none_args = [a for a in args if a is not type(None)]
    if len(non_none_args) == 1:
        return (non_none_args[0],)
    if len(non_none_args) > 1:
        return tuple(non_none_args)
    return ()


def unwrap_annotated(annotation) -> tuple[Any, CommandOptionSpec | None]:
    """Return the base annotation and command option metadata, if any."""

    if typing.get_origin(annotation) is not typing.Annotated:
        return annotation, None

    args = typing.get_args(annotation)
    base_annotation = args[0]
    option_specs = [arg for arg in args[1:] if isinstance(arg, CommandOptionSpec)]
    if len(option_specs) > 1:
        raise ValueError("同一个参数不能声明多个 filter.option(...) 元数据。")

    return base_annotation, option_specs[0] if option_specs else None


# 标准指令受到 wake_prefix 的制约。
class CommandFilter(HandlerFilter):
    """标准指令过滤器"""

    def __init__(
        self,
        command_name: str,
        alias: set | None = None,
        handler_md: StarHandlerMetadata | None = None,
        parent_command_names: list[str] | None = None,
    ) -> None:
        self.command_name = command_name
        self.alias = alias if alias else set()
        self._original_command_name = command_name
        self.parent_command_names = (
            parent_command_names if parent_command_names is not None else [""]
        )
        if handler_md:
            self.init_handler_md(handler_md)
        self.custom_filter_list: list[CustomFilter] = []
        self.handler_params: list[CommandParamSpec] = []
        self._option_param_map: dict[str, CommandParamSpec] = {}

        # Cache for complete command names list
        self._cmpl_cmd_names: list | None = None

    def print_types(self):
        parts = []
        for param in self.handler_params:
            type_display = self._type_name(param)
            option_display = ""
            if param.option:
                option_display = f"[{'/'.join(param.option.names)}]"

            if param.has_default:
                parts.append(
                    f"{param.name}{option_display}({type_display})={param.default},"
                )
            else:
                parts.append(f"{param.name}{option_display}({type_display}),")
        result = "".join(parts).rstrip(",")
        return result

    def format_invocation(
        self,
        command_name: str | None = None,
        include_aliases: bool = False,
    ) -> str:
        display_name = command_name or self.get_complete_command_names()[0]
        params_display = self.print_types()
        result = display_name
        if params_display:
            result += f" ({params_display})"
        if include_aliases and self.alias:
            aliases = ", ".join(sorted(self.alias))
            result += f" [aliases: {aliases}]"
        return result

    def init_handler_md(self, handle_md: StarHandlerMetadata) -> None:
        self.handler_md = handle_md
        signature = inspect.signature(self.handler_md.handler)
        self.handler_params = []
        self._option_param_map = {}
        idx = 0
        seen_greedy = False
        for k, v in signature.parameters.items():
            if idx < 2:
                # 忽略前两个参数，即 self 和 event
                idx += 1
                continue

            annotation, option_spec = unwrap_annotated(v.annotation)
            param_spec = CommandParamSpec(
                name=k,
                annotation=annotation,
                default=v.default,
                option=option_spec,
            )

            if param_spec.is_greedy and option_spec is not None:
                raise ValueError(
                    f"参数 '{k}' 不能同时声明 GreedyStr 和 filter.option(...)。",
                )

            if param_spec.is_greedy:
                seen_greedy = True
            elif seen_greedy and option_spec is None:
                raise ValueError(
                    "GreedyStr 后不能再声明其他位置参数。",
                )

            if option_spec is not None:
                for option_name in option_spec.names:
                    if option_name in self._option_param_map:
                        raise ValueError(f"重复的 option 名称: {option_name}")
                    self._option_param_map[option_name] = param_spec

            self.handler_params.append(param_spec)

    def get_handler_md(self) -> StarHandlerMetadata:
        return self.handler_md

    def add_custom_filter(self, custom_filter: CustomFilter) -> None:
        self.custom_filter_list.append(custom_filter)

    def custom_filter_ok(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        for custom_filter in self.custom_filter_list:
            if not custom_filter.filter(event, cfg):
                return False
        return True

    def _type_name(self, param: CommandParamSpec) -> str:
        if param.annotation is inspect.Parameter.empty:
            if param.has_default:
                return type(param.default).__name__
            return "str"
        if isinstance(param.annotation, type):
            return param.annotation.__name__
        return str(param.annotation)

    def _is_bool_annotation(self, annotation: Any) -> bool:
        if annotation is bool:
            return True
        origin = typing.get_origin(annotation)
        if origin in (typing.Union, types.UnionType):
            non_none_types = unwrap_optional(annotation)
            return len(non_none_types) == 1 and non_none_types[0] is bool
        return False

    def _is_bool_option(self, param: CommandParamSpec) -> bool:
        return isinstance(param.default, bool) or self._is_bool_annotation(
            param.annotation
        )

    def _convert_bool_value(self, param_name: str, raw_value: str) -> bool:
        lower_param = str(raw_value).lower()
        if lower_param in ["true", "yes", "1"]:
            return True
        if lower_param in ["false", "no", "0"]:
            return False
        raise ValueError(
            f"参数 {param_name} 必须是布尔值（true/false, yes/no, 1/0）。",
        )

    def _looks_like_bool_literal(self, raw_value: str) -> bool:
        return str(raw_value).lower() in {"true", "false", "yes", "no", "1", "0"}

    def _convert_param_value(
        self,
        raw_value: str,
        param: CommandParamSpec,
    ) -> Any:
        try:
            if param.default is None:
                if (
                    param.option is not None
                    and param.annotation is not inspect.Parameter.empty
                ):
                    origin = typing.get_origin(param.annotation)
                    if origin in (typing.Union, types.UnionType):
                        non_none_types = unwrap_optional(param.annotation)
                        if len(non_none_types) == 1:
                            return non_none_types[0](raw_value)
                    elif (
                        isinstance(param.annotation, type)
                        and param.annotation is not Any
                    ):
                        return param.annotation(raw_value)

                if raw_value.isdigit():
                    return int(raw_value)
                return raw_value

            if isinstance(param.default, str):
                return raw_value
            if isinstance(param.default, bool):
                return self._convert_bool_value(param.name, raw_value)
            if isinstance(param.default, int):
                return int(raw_value)
            if isinstance(param.default, float):
                return float(raw_value)

            annotation = param.annotation
            if annotation in (inspect.Parameter.empty, Any):
                return raw_value

            origin = typing.get_origin(annotation)
            if origin in (typing.Union, types.UnionType):
                non_none_types = unwrap_optional(annotation)
                if len(non_none_types) == 1:
                    return non_none_types[0](raw_value)
                return raw_value

            if isinstance(annotation, type):
                return annotation(raw_value)
            return raw_value
        except ValueError:
            raise ValueError(
                f"参数 {param.name} 类型错误。完整参数: {self.print_types()}",
            )

    def _match_option_token(
        self,
        token: str,
    ) -> tuple[CommandParamSpec | None, str | None]:
        option_name = token
        inline_value = None

        if "=" in token:
            option_name, inline_value = token.split("=", 1)

        param = self._option_param_map.get(option_name)
        if param is None:
            return None, None

        return param, inline_value

    def validate_and_convert_params(self, params: list[Any]) -> dict[str, Any]:
        """将参数列表 params 转换为参数字典。"""

        result = {}
        positional_tokens: list[str] = []
        parsed_options: dict[str, Any] = {}
        token_idx = 0
        parse_options = True

        while token_idx < len(params):
            token = params[token_idx]
            if parse_options and token == "--":
                parse_options = False
                token_idx += 1
                continue

            if not parse_options:
                positional_tokens.append(token)
                token_idx += 1
                continue

            param, inline_value = self._match_option_token(token)
            if param is None:
                positional_tokens.append(token)
                token_idx += 1
                continue

            if param.name in parsed_options:
                raise ValueError(f"重复的 option: {token}")

            if self._is_bool_option(param):
                if inline_value is None:
                    if (
                        token_idx + 1 < len(params)
                        and self._looks_like_bool_literal(params[token_idx + 1])
                    ):
                        parsed_options[param.name] = self._convert_param_value(
                            params[token_idx + 1],
                            param,
                        )
                        token_idx += 2
                        continue
                    parsed_options[param.name] = True
                else:
                    parsed_options[param.name] = self._convert_param_value(
                        inline_value, param
                    )
                token_idx += 1
                continue

            if inline_value is not None:
                parsed_options[param.name] = self._convert_param_value(
                    inline_value, param
                )
                token_idx += 1
                continue

            if token_idx + 1 >= len(params):
                raise ValueError(
                    f"选项 {token} 缺少值。完整参数: {self.print_types()}",
                )

            parsed_options[param.name] = self._convert_param_value(
                params[token_idx + 1], param
            )
            token_idx += 2

        positional_idx = 0
        for param in self.handler_params:
            if param.option is not None:
                if param.name in parsed_options:
                    result[param.name] = parsed_options[param.name]
                elif param.has_default:
                    result[param.name] = param.default
                else:
                    raise ValueError(
                        f"必要参数缺失。该指令完整参数: {self.print_types()}",
                    )
                continue

            if param.is_greedy:
                result[param.name] = " ".join(positional_tokens[positional_idx:])
                positional_idx = len(positional_tokens)
                continue

            if positional_idx >= len(positional_tokens):
                if param.is_required:
                    raise ValueError(
                        f"必要参数缺失。该指令完整参数: {self.print_types()}",
                    )
                result[param.name] = param.default
                continue

            result[param.name] = self._convert_param_value(
                positional_tokens[positional_idx], param
            )
            positional_idx += 1

        if positional_idx < len(positional_tokens):
            raise ValueError(
                f"参数过多。该指令完整参数: {self.print_types()}",
            )

        return result

    def get_complete_command_names(self):
        if self._cmpl_cmd_names is not None:
            return self._cmpl_cmd_names
        self._cmpl_cmd_names = [
            f"{parent} {cmd}" if parent else cmd
            for cmd in [self.command_name] + list(self.alias)
            for parent in self.parent_command_names or [""]
        ]
        return self._cmpl_cmd_names

    def equals(self, message_str: str) -> bool:
        for full_cmd in self.get_complete_command_names():
            if message_str == full_cmd:
                return True
        return False

    def _match_message_tokens(
        self,
        message_tokens: list[str],
    ) -> tuple[list[str], list[str]] | None:
        best_match: tuple[list[str], list[str]] | None = None

        for full_cmd in self.get_complete_command_names():
            command_tokens = full_cmd.split(" ")
            if message_tokens[: len(command_tokens)] != command_tokens:
                continue

            if best_match is None or len(command_tokens) > len(best_match[0]):
                best_match = (command_tokens, message_tokens[len(command_tokens) :])

        return best_match

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        if not event.is_at_or_wake_command:
            return False

        if not self.custom_filter_ok(event, cfg):
            return False

        message_tokens = tokenize_command_args(event.get_message_str().strip())
        matched = self._match_message_tokens(message_tokens)
        if matched is None:
            return False

        _, params_tokens = matched
        params = {}
        try:
            params = self.validate_and_convert_params(params_tokens)
        except ValueError as e:
            raise e

        event.set_extra("parsed_params", params)

        return True
