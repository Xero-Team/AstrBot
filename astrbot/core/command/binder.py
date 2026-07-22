import difflib
import enum
from typing import Any

from .diagnostics import (
    CommandDiagnostic,
    CommandError,
    CommandErrorCode,
    CommandHintCode,
)
from .models import BoundCommand, CommandInvocation, CommandWord, SourceSpan
from .schema import CommandParamSpec, CommandSchema

_BOOL_VALUES = {
    "true": True,
    "yes": True,
    "1": True,
    "false": False,
    "no": False,
    "0": False,
}


class CommandBinder:
    def bind(
        self, schema: CommandSchema, invocation: CommandInvocation
    ) -> BoundCommand:
        positional: list[CommandWord] = []
        parsed_options: dict[str, Any] = {}
        words = invocation.words
        parse_options = True
        index = 0
        while index < len(words):
            word = words[index]
            token = word.value
            if parse_options and token == "--":
                parse_options = False
                index += 1
                continue
            option_name, separator, inline = token.partition("=")
            option_index = schema.option_index(option_name) if parse_options else None
            if option_index is not None:
                param = schema.params[option_index]
                if param.name in parsed_options:
                    self._raise(
                        CommandErrorCode.DUPLICATE_OPTION,
                        word.span,
                        {"option": option_name},
                    )
                if param.is_bool:
                    if separator:
                        value = self._convert(inline, param, word.span)
                    elif (
                        index + 1 < len(words)
                        and words[index + 1].value.lower() in _BOOL_VALUES
                    ):
                        index += 1
                        value = self._convert(
                            words[index].value, param, words[index].span
                        )
                    else:
                        value = True
                elif separator:
                    value = self._convert(inline, param, word.span)
                else:
                    if index + 1 >= len(words):
                        self._raise(
                            CommandErrorCode.MISSING_OPTION_VALUE,
                            word.span,
                            {"option": option_name},
                        )
                    index += 1
                    value = self._convert(words[index].value, param, words[index].span)
                parsed_options[param.name] = value
                index += 1
                continue
            if parse_options and token.startswith("-") and token != "-":
                next_positional = self._next_positional(schema, len(positional))
                if not (
                    next_positional
                    and next_positional.is_numeric
                    and self._is_number(token, next_positional.input_type)
                ):
                    params: dict[str, str | int] = {"option": option_name}
                    hint = CommandHintCode.USE_OPTION_TERMINATOR
                    matches = difflib.get_close_matches(
                        option_name, schema.option_names, n=1, cutoff=0.6
                    )
                    if matches:
                        params["suggestion"] = matches[0]
                        hint = CommandHintCode.DID_YOU_MEAN
                    self._raise(
                        CommandErrorCode.UNKNOWN_OPTION, word.span, params, hint
                    )
            positional.append(word)
            index += 1

        result: dict[str, Any] = {}
        positional_index = 0
        for param in schema.params:
            if param.option:
                if param.name in parsed_options:
                    result[param.name] = parsed_options[param.name]
                elif param.has_default:
                    result[param.name] = param.default
                else:
                    self._raise(
                        CommandErrorCode.MISSING_ARGUMENT,
                        invocation.argument_span or self._end_span(invocation),
                        {"argument": param.name},
                    )
                continue
            if param.is_greedy:
                if positional_index >= len(positional):
                    if param.has_default:
                        result[param.name] = param.default
                    else:
                        self._raise(
                            CommandErrorCode.MISSING_ARGUMENT,
                            invocation.argument_span or self._end_span(invocation),
                            {"argument": param.name},
                        )
                else:
                    result[param.name] = " ".join(
                        word.value for word in positional[positional_index:]
                    )
                    positional_index = len(positional)
                continue
            if positional_index >= len(positional):
                if param.has_default:
                    result[param.name] = param.default
                else:
                    self._raise(
                        CommandErrorCode.MISSING_ARGUMENT,
                        invocation.argument_span or self._end_span(invocation),
                        {"argument": param.name},
                    )
                continue
            word = positional[positional_index]
            result[param.name] = self._convert(word.value, param, word.span)
            positional_index += 1

        if positional_index < len(positional):
            first = positional[positional_index]
            last = positional[-1]
            self._raise(
                CommandErrorCode.TOO_MANY_ARGUMENTS,
                SourceSpan(first.span.start, last.span.end),
            )
        return BoundCommand(invocation, result)

    @staticmethod
    def _next_positional(
        schema: CommandSchema, consumed: int
    ) -> CommandParamSpec | None:
        positionals = [param for param in schema.params if param.option is None]
        return positionals[consumed] if consumed < len(positionals) else None

    @staticmethod
    def _is_number(raw: str, value_type: Any) -> bool:
        try:
            value_type(raw)
        except ValueError:
            return False
        return True

    def _convert(self, raw: str, param: CommandParamSpec, span: SourceSpan) -> Any:
        try:
            if param.input_type is bool:
                value = _BOOL_VALUES[raw.lower()]
            else:
                value = param.input_type(raw)
            if isinstance(param.value_type, type) and issubclass(
                param.value_type, enum.Enum
            ):
                value = param.value_type(value)
            if param.literals and value not in param.literals:
                raise ValueError
            return value
        except Exception:
            self._raise(
                CommandErrorCode.INVALID_ARGUMENT,
                span,
                {"argument": param.name, "expected": param.display_type},
            )

    @staticmethod
    def _end_span(invocation: CommandInvocation) -> SourceSpan:
        end = len(invocation.source)
        return SourceSpan(end, end)

    @staticmethod
    def _raise(
        code: CommandErrorCode,
        span: SourceSpan,
        params: dict[str, str | int] | None = None,
        hint: CommandHintCode | None = None,
    ) -> None:
        raise CommandError(CommandDiagnostic(code, span, params or {}, hint))
