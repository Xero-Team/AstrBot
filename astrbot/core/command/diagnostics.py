import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from .models import SourceSpan


class CommandErrorCategory(StrEnum):
    SYNTAX = "syntax"
    RESOLUTION = "resolution"
    BINDING = "binding"
    SCHEMA = "schema"


class CommandErrorCode(StrEnum):
    SOURCE_TOO_LONG = "syntax.source_too_long"
    TOO_MANY_WORDS = "syntax.too_many_words"
    TOO_MANY_FRAGMENTS = "syntax.too_many_fragments"
    NUL_CHARACTER = "syntax.nul_character"
    DANGLING_ESCAPE = "syntax.dangling_escape"
    UNCLOSED_SINGLE_QUOTE = "syntax.unclosed_single_quote"
    UNCLOSED_DOUBLE_QUOTE = "syntax.unclosed_double_quote"
    UNSUPPORTED_PARAMETER_EXPANSION = "syntax.unsupported_parameter_expansion"
    UNSUPPORTED_COMMAND_SUBSTITUTION = "syntax.unsupported_command_substitution"
    UNSUPPORTED_ARITHMETIC_EXPANSION = "syntax.unsupported_arithmetic_expansion"
    UNSUPPORTED_DOLLAR_SINGLE_QUOTE = "syntax.unsupported_dollar_single_quote"
    UNSUPPORTED_TILDE_EXPANSION = "syntax.unsupported_tilde_expansion"
    UNSUPPORTED_PATHNAME_EXPANSION = "syntax.unsupported_pathname_expansion"
    UNSUPPORTED_OPERATOR = "syntax.unsupported_operator"
    UNSUPPORTED_COMMENT = "syntax.unsupported_comment"
    UNSUPPORTED_COMMAND_SEPARATOR = "syntax.unsupported_command_separator"
    INCOMPLETE_COMMAND_GROUP = "resolution.incomplete_command_group"
    UNKNOWN_SUBCOMMAND = "resolution.unknown_subcommand"
    UNKNOWN_OPTION = "binding.unknown_option"
    DUPLICATE_OPTION = "binding.duplicate_option"
    MISSING_OPTION_VALUE = "binding.missing_option_value"
    MISSING_ARGUMENT = "binding.missing_argument"
    TOO_MANY_ARGUMENTS = "binding.too_many_arguments"
    INVALID_ARGUMENT = "binding.invalid_argument"
    UNSUPPORTED_SIGNATURE = "schema.unsupported_signature"

    @property
    def category(self) -> CommandErrorCategory:
        return CommandErrorCategory(self.value.split(".", 1)[0])


class CommandHintCode(StrEnum):
    QUOTE_LITERAL = "quote_literal"
    ESCAPE_LITERAL = "escape_literal"
    USE_OPTION_TERMINATOR = "use_option_terminator"
    DID_YOU_MEAN = "did_you_mean"


DiagnosticParam = str | int


@dataclass(frozen=True, slots=True)
class CommandDiagnostic:
    code: CommandErrorCode
    span: SourceSpan
    params: Mapping[str, DiagnosticParam]
    hint_code: CommandHintCode | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable protocol representation."""

        return {
            "code": self.code.value,
            "category": self.code.category.value,
            "span": {"start": self.span.start, "end": self.span.end},
            "params": dict(self.params),
            "hint_code": self.hint_code.value if self.hint_code else None,
        }


class CommandError(ValueError):
    def __init__(self, diagnostic: CommandDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.code.value)


class CommandSyntaxError(CommandError):
    pass


_MESSAGES: dict[str, dict[CommandErrorCode, str]] = {
    "en-US": {
        CommandErrorCode.SOURCE_TOO_LONG: "Command input exceeds {limit} characters.",
        CommandErrorCode.TOO_MANY_WORDS: "Command input exceeds {limit} arguments.",
        CommandErrorCode.TOO_MANY_FRAGMENTS: "Command input exceeds {limit} word fragments.",
        CommandErrorCode.NUL_CHARACTER: "NUL is not allowed in command input.",
        CommandErrorCode.DANGLING_ESCAPE: "The trailing backslash has nothing to escape.",
        CommandErrorCode.UNCLOSED_SINGLE_QUOTE: "The single-quoted string is not closed.",
        CommandErrorCode.UNCLOSED_DOUBLE_QUOTE: "The double-quoted string is not closed.",
        CommandErrorCode.UNSUPPORTED_PARAMETER_EXPANSION: "Parameter expansion is not supported.",
        CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION: "Command substitution is not supported.",
        CommandErrorCode.UNSUPPORTED_ARITHMETIC_EXPANSION: "Arithmetic expansion is not supported.",
        CommandErrorCode.UNSUPPORTED_DOLLAR_SINGLE_QUOTE: "Dollar single quotes are not supported.",
        CommandErrorCode.UNSUPPORTED_TILDE_EXPANSION: "Tilde expansion is not supported.",
        CommandErrorCode.UNSUPPORTED_PATHNAME_EXPANSION: "Pathname expansion is not supported.",
        CommandErrorCode.UNSUPPORTED_OPERATOR: "Shell operators are not supported.",
        CommandErrorCode.UNSUPPORTED_COMMENT: "Shell comments are not supported.",
        CommandErrorCode.UNSUPPORTED_COMMAND_SEPARATOR: "Unquoted newlines are not supported.",
        CommandErrorCode.INCOMPLETE_COMMAND_GROUP: "Choose a subcommand for {command}. Available:\n{available}",
        CommandErrorCode.UNKNOWN_SUBCOMMAND: "Unknown subcommand for {command}: {subcommand}. Available:\n{available}",
        CommandErrorCode.UNKNOWN_OPTION: "Unknown option: {option}.",
        CommandErrorCode.DUPLICATE_OPTION: "Option was provided more than once: {option}.",
        CommandErrorCode.MISSING_OPTION_VALUE: "Option requires a value: {option}.",
        CommandErrorCode.MISSING_ARGUMENT: "Required argument is missing: {argument}.",
        CommandErrorCode.TOO_MANY_ARGUMENTS: "Too many command arguments.",
        CommandErrorCode.INVALID_ARGUMENT: "Invalid value for {argument}; expected {expected}.",
        CommandErrorCode.UNSUPPORTED_SIGNATURE: "Unsupported command signature: {reason}.",
    },
    "zh-CN": {
        CommandErrorCode.SOURCE_TOO_LONG: "指令输入超过 {limit} 个字符。",
        CommandErrorCode.TOO_MANY_WORDS: "指令输入超过 {limit} 个参数。",
        CommandErrorCode.TOO_MANY_FRAGMENTS: "指令输入超过 {limit} 个词片段。",
        CommandErrorCode.NUL_CHARACTER: "指令输入不能包含 NUL 字符。",
        CommandErrorCode.DANGLING_ESCAPE: "末尾反斜杠缺少要转义的字符。",
        CommandErrorCode.UNCLOSED_SINGLE_QUOTE: "单引号字符串未闭合。",
        CommandErrorCode.UNCLOSED_DOUBLE_QUOTE: "双引号字符串未闭合。",
        CommandErrorCode.UNSUPPORTED_PARAMETER_EXPANSION: "Orbit 不支持参数展开。",
        CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION: "Orbit 不支持命令替换。",
        CommandErrorCode.UNSUPPORTED_ARITHMETIC_EXPANSION: "Orbit 不支持算术展开。",
        CommandErrorCode.UNSUPPORTED_DOLLAR_SINGLE_QUOTE: "Orbit 不支持美元单引号语法。",
        CommandErrorCode.UNSUPPORTED_TILDE_EXPANSION: "Orbit 不支持波浪号展开。",
        CommandErrorCode.UNSUPPORTED_PATHNAME_EXPANSION: "Orbit 不支持路径名展开。",
        CommandErrorCode.UNSUPPORTED_OPERATOR: "Orbit 不支持 shell 操作符。",
        CommandErrorCode.UNSUPPORTED_COMMENT: "Orbit 不支持 shell 注释。",
        CommandErrorCode.UNSUPPORTED_COMMAND_SEPARATOR: "Orbit 不支持未引用的换行。",
        CommandErrorCode.INCOMPLETE_COMMAND_GROUP: "请为 {command} 选择子指令。可用子指令：\n{available}",
        CommandErrorCode.UNKNOWN_SUBCOMMAND: "{command} 下不存在子指令 {subcommand}。可用子指令：\n{available}",
        CommandErrorCode.UNKNOWN_OPTION: "未知选项：{option}。",
        CommandErrorCode.DUPLICATE_OPTION: "选项重复：{option}。",
        CommandErrorCode.MISSING_OPTION_VALUE: "选项缺少值：{option}。",
        CommandErrorCode.MISSING_ARGUMENT: "缺少必要参数：{argument}。",
        CommandErrorCode.TOO_MANY_ARGUMENTS: "指令参数过多。",
        CommandErrorCode.INVALID_ARGUMENT: "参数 {argument} 的值无效，应为 {expected}。",
        CommandErrorCode.UNSUPPORTED_SIGNATURE: "不支持的指令签名：{reason}。",
    },
}

_HINTS = {
    "en-US": {
        CommandHintCode.QUOTE_LITERAL: "Quote the character to pass it literally.",
        CommandHintCode.ESCAPE_LITERAL: "Escape the character to pass it literally.",
        CommandHintCode.USE_OPTION_TERMINATOR: "Use -- before a dash-prefixed positional value.",
        CommandHintCode.DID_YOU_MEAN: "Did you mean {suggestion}?",
    },
    "zh-CN": {
        CommandHintCode.QUOTE_LITERAL: "如需传入字面字符，请使用引号。",
        CommandHintCode.ESCAPE_LITERAL: "如需传入字面字符，请使用反斜杠转义。",
        CommandHintCode.USE_OPTION_TERMINATOR: "在以短横线开头的位置参数前使用 --。",
        CommandHintCode.DID_YOU_MEAN: "你是否想使用 {suggestion}？",
    },
}


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char) or unicodedata.category(char) in {
            "Cc",
            "Cf",
            "Me",
            "Mn",
        }:
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def render_diagnostic(
    diagnostic: CommandDiagnostic,
    source: str,
    locale: str = "zh-CN",
) -> str:
    """Render a diagnostic at the presentation boundary."""

    messages = _MESSAGES.get(locale, _MESSAGES["en-US"])
    template = messages.get(diagnostic.code, diagnostic.code.value)
    message = template.format_map(diagnostic.params)

    start = min(diagnostic.span.start, len(source))
    end = min(max(diagnostic.span.end, start), len(source))
    line_start = (
        max(
            source.rfind("\n", 0, start),
            source.rfind("\r", 0, start),
        )
        + 1
    )
    line_breaks = tuple(
        position
        for separator in ("\r", "\n")
        if (position := source.find(separator, start)) >= 0
    )
    line_end = min(line_breaks, default=len(source))
    raw_line = source[line_start:line_end]
    excerpt = raw_line.expandtabs(4)
    prefix = source[line_start:start].expandtabs(4)
    selection_end = min(max(end, start + 1), line_end)
    through_selection = source[line_start:selection_end].expandtabs(4)
    prefix_width = _display_width(prefix)
    selected_width = _display_width(through_selection) - prefix_width
    caret = " " * prefix_width + "^" * max(1, selected_width)
    rendered = f"{message}\n{excerpt}\n{caret}"
    if diagnostic.hint_code:
        hint = _HINTS.get(locale, _HINTS["en-US"])[diagnostic.hint_code]
        rendered += "\n" + hint.format_map(diagnostic.params)
    return rendered
