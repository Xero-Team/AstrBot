import re


class CommandParseError(ValueError):
    """Raised when command argument tokenization fails."""


class CommandTokens:
    def __init__(self) -> None:
        self.tokens = []
        self.len = 0

    def get(self, idx: int) -> str | None:
        if idx >= self.len:
            return None
        return self.tokens[idx]


def _is_escapable_char(char: str) -> bool:
    return char.isspace() or char in {"\\", "'", '"'}


def tokenize_command_args(message: str) -> list[str]:
    """Tokenize command arguments with lightweight shell-like quoting.

    Supported features:
    - Single and double quotes
    - Backslash escapes for whitespace, quotes, and backslashes
    - Adjacent quoted and unquoted segments in the same token

    Args:
        message: Raw command argument string.

    Returns:
        A list of parsed argument tokens.

    Raises:
        CommandParseError: If an unmatched quote or dangling escape is found.
    """

    tokens: list[str] = []
    current: list[str] = []
    quote_char = ""
    token_started = False
    index = 0

    while index < len(message):
        char = message[index]

        if quote_char:
            if char == "\\":
                if index + 1 >= len(message):
                    raise CommandParseError("参数解析失败：反斜杠转义未完成。")
                next_char = message[index + 1]
                if _is_escapable_char(next_char) or next_char == quote_char:
                    current.append(next_char)
                    index += 2
                    continue
                current.append(char)
                index += 1
                continue

            if char == quote_char:
                quote_char = ""
                token_started = True
                index += 1
                continue

            current.append(char)
            index += 1
            continue

        if char.isspace():
            if token_started:
                tokens.append("".join(current))
                current.clear()
                token_started = False
            index += 1
            continue

        if char in {"'", '"'}:
            quote_char = char
            token_started = True
            index += 1
            continue

        if char == "\\":
            if index + 1 >= len(message):
                raise CommandParseError("参数解析失败：反斜杠转义未完成。")
            next_char = message[index + 1]
            if _is_escapable_char(next_char):
                current.append(next_char)
                token_started = True
                index += 2
                continue
            current.append(char)
            token_started = True
            index += 1
            continue

        current.append(char)
        token_started = True
        index += 1

    if quote_char:
        quote_name = "双" if quote_char == '"' else "单"
        raise CommandParseError(f"参数解析失败：未闭合的{quote_name}引号。")

    if token_started:
        tokens.append("".join(current))

    return tokens


class CommandParserMixin:
    def parse_commands(self, message: str):
        cmd_tokens = CommandTokens()
        cmd_tokens.tokens = tokenize_command_args(message)
        cmd_tokens.len = len(cmd_tokens.tokens)
        return cmd_tokens

    def regex_match(self, message: str, command: str) -> bool:
        return re.search(command, message, re.MULTILINE) is not None
