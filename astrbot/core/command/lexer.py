from .diagnostics import (
    CommandDiagnostic,
    CommandErrorCode,
    CommandHintCode,
    CommandSyntaxError,
)
from .models import (
    CommandInvocation,
    CommandWord,
    SourceSpan,
    WordFragment,
    WordFragmentKind,
)

MAX_SOURCE_LENGTH = 64 * 1024
MAX_WORDS = 4096
MAX_FRAGMENTS = 16384

_OPERATORS = frozenset("|&;<>()")
_GLOB_CHARS = frozenset("*?[")


class CommandLexer:
    """Deterministic, single-pass lexer for the Orbit POSIX word subset."""

    def __init__(
        self,
        *,
        max_source_length: int = MAX_SOURCE_LENGTH,
        max_words: int = MAX_WORDS,
        max_fragments: int = MAX_FRAGMENTS,
    ) -> None:
        self.max_source_length = max_source_length
        self.max_words = max_words
        self.max_fragments = max_fragments

    def lex(self, source: str, *, offset: int = 0) -> CommandInvocation:
        if len(source) > self.max_source_length:
            self._raise(
                CommandErrorCode.SOURCE_TOO_LONG,
                offset,
                offset + len(source),
                {"limit": self.max_source_length},
            )

        words: list[CommandWord] = []
        fragments: list[WordFragment] = []
        value_parts: list[str] = []
        word_start = 0
        word_started = False
        fragment_count = 0
        index = 0

        def add_fragment(value: str, start: int, end: int, kind: WordFragmentKind):
            nonlocal fragment_count
            fragment_count += 1
            if fragment_count > self.max_fragments:
                self._raise(
                    CommandErrorCode.TOO_MANY_FRAGMENTS,
                    offset + start,
                    offset + end,
                    {"limit": self.max_fragments},
                )
            fragments.append(
                WordFragment(value, SourceSpan(offset + start, offset + end), kind)
            )
            value_parts.append(value)

        def finish_word(end: int) -> None:
            nonlocal word_started
            if not word_started:
                return
            if len(words) >= self.max_words:
                self._raise(
                    CommandErrorCode.TOO_MANY_WORDS,
                    offset + word_start,
                    offset + end,
                    {"limit": self.max_words},
                )
            words.append(
                CommandWord(
                    "".join(value_parts),
                    SourceSpan(offset + word_start, offset + end),
                    tuple(fragments),
                )
            )
            fragments.clear()
            value_parts.clear()
            word_started = False

        while index < len(source):
            char = source[index]
            if char == "\0":
                self._raise(
                    CommandErrorCode.NUL_CHARACTER, offset + index, offset + index + 1
                )
            if char in " \t":
                finish_word(index)
                index += 1
                continue
            if char in "\r\n":
                self._raise(
                    CommandErrorCode.UNSUPPORTED_COMMAND_SEPARATOR,
                    offset + index,
                    offset + index + 1,
                )
            starting_word = not word_started
            if starting_word:
                word_started = True
                word_start = index

            if char == "\\":
                if index + 1 >= len(source):
                    self._raise(
                        CommandErrorCode.DANGLING_ESCAPE,
                        offset + index,
                        offset + index + 1,
                    )
                next_char = source[index + 1]
                if next_char == "\n":
                    if starting_word:
                        word_started = False
                    index += 2
                    continue
                if next_char == "\0":
                    self._raise(
                        CommandErrorCode.NUL_CHARACTER,
                        offset + index + 1,
                        offset + index + 2,
                    )
                add_fragment(next_char, index, index + 2, WordFragmentKind.ESCAPED)
                index += 2
                continue

            if char == "'":
                start = index
                index += 1
                content_start = index
                while index < len(source) and source[index] != "'":
                    if source[index] == "\0":
                        self._raise(
                            CommandErrorCode.NUL_CHARACTER,
                            offset + index,
                            offset + index + 1,
                        )
                    index += 1
                if index >= len(source):
                    self._raise(
                        CommandErrorCode.UNCLOSED_SINGLE_QUOTE,
                        offset + start,
                        offset + len(source),
                    )
                add_fragment(
                    source[content_start:index],
                    start,
                    index + 1,
                    WordFragmentKind.SINGLE_QUOTED,
                )
                index += 1
                continue

            if char == '"':
                start = index
                index += 1
                double_parts: list[str] = []
                while index < len(source) and source[index] != '"':
                    inner = source[index]
                    if inner == "\0":
                        self._raise(
                            CommandErrorCode.NUL_CHARACTER,
                            offset + index,
                            offset + index + 1,
                        )
                    if inner == "$":
                        self._unsupported_dollar(source, index, offset)
                    if inner == "`":
                        self._raise(
                            CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION,
                            offset + index,
                            offset + index + 1,
                        )
                    if inner == "\\" and index + 1 < len(source):
                        escaped = source[index + 1]
                        if escaped == "\n":
                            index += 2
                            continue
                        if escaped in {"$", "`", "\\", '"'}:
                            double_parts.append(escaped)
                            index += 2
                            continue
                        double_parts.append("\\")
                        index += 1
                        continue
                    double_parts.append(inner)
                    index += 1
                if index >= len(source):
                    self._raise(
                        CommandErrorCode.UNCLOSED_DOUBLE_QUOTE,
                        offset + start,
                        offset + len(source),
                    )
                add_fragment(
                    "".join(double_parts),
                    start,
                    index + 1,
                    WordFragmentKind.DOUBLE_QUOTED,
                )
                index += 1
                continue

            if char == "$":
                self._unsupported_dollar(source, index, offset)
            if char == "`":
                self._raise(
                    CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION,
                    offset + index,
                    offset + index + 1,
                )
            if char == "~" and len(value_parts) == 0:
                self._raise(
                    CommandErrorCode.UNSUPPORTED_TILDE_EXPANSION,
                    offset + index,
                    offset + index + 1,
                )
            if char in _GLOB_CHARS:
                self._raise(
                    CommandErrorCode.UNSUPPORTED_PATHNAME_EXPANSION,
                    offset + index,
                    offset + index + 1,
                    hint=CommandHintCode.QUOTE_LITERAL,
                )
            if char in _OPERATORS:
                self._raise(
                    CommandErrorCode.UNSUPPORTED_OPERATOR,
                    offset + index,
                    offset + index + 1,
                    hint=CommandHintCode.QUOTE_LITERAL,
                )
            if char == "#" and len(value_parts) == 0:
                self._raise(
                    CommandErrorCode.UNSUPPORTED_COMMENT,
                    offset + index,
                    offset + index + 1,
                )

            start = index
            while index < len(source):
                current = source[index]
                if current in " \t\r\n\\'\"$`~*?[|&;<>()\0":
                    break
                if current == "#" and index == word_start:
                    break
                index += 1
            if index == start:
                add_fragment(char, index, index + 1, WordFragmentKind.UNQUOTED)
                index += 1
            else:
                add_fragment(
                    source[start:index], start, index, WordFragmentKind.UNQUOTED
                )

        finish_word(len(source))
        return CommandInvocation(source, tuple(words))

    def _unsupported_dollar(self, source: str, index: int, offset: int) -> None:
        code = CommandErrorCode.UNSUPPORTED_PARAMETER_EXPANSION
        end = index + 1
        if source.startswith("$'", index):
            code = CommandErrorCode.UNSUPPORTED_DOLLAR_SINGLE_QUOTE
            end = min(len(source), index + 2)
        elif source.startswith("$((", index):
            code = CommandErrorCode.UNSUPPORTED_ARITHMETIC_EXPANSION
            end = min(len(source), index + 3)
        elif source.startswith("$(", index):
            code = CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION
            end = min(len(source), index + 2)
        self._raise(
            code, offset + index, offset + end, hint=CommandHintCode.QUOTE_LITERAL
        )

    @staticmethod
    def _raise(
        code: CommandErrorCode,
        start: int,
        end: int,
        params: dict[str, str | int] | None = None,
        *,
        hint: CommandHintCode | None = None,
    ) -> None:
        raise CommandSyntaxError(
            CommandDiagnostic(code, SourceSpan(start, end), params or {}, hint)
        )


def parse_arguments(source: str) -> CommandInvocation:
    return CommandLexer().lex(source)
