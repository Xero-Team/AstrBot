from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """A half-open source range measured in Unicode code points."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid source span")


class WordFragmentKind(StrEnum):
    UNQUOTED = "unquoted"
    ESCAPED = "escaped"
    SINGLE_QUOTED = "single_quoted"
    DOUBLE_QUOTED = "double_quoted"


@dataclass(frozen=True, slots=True)
class WordFragment:
    value: str
    span: SourceSpan
    kind: WordFragmentKind


@dataclass(frozen=True, slots=True)
class CommandWord:
    value: str
    span: SourceSpan
    fragments: tuple[WordFragment, ...]


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    source: str
    words: tuple[CommandWord, ...]
    command_span: SourceSpan | None = None
    argument_span: SourceSpan | None = None

    @property
    def argv(self) -> tuple[str, ...]:
        return tuple(word.value for word in self.words)


class CommandResolutionKind(StrEnum):
    MATCHED = "matched"
    INCOMPLETE_GROUP = "incomplete_group"
    UNKNOWN_SUBCOMMAND = "unknown_subcommand"
    UNKNOWN_ROOT = "unknown_root"


@dataclass(frozen=True, slots=True)
class CommandResolution:
    kind: CommandResolutionKind
    source: str
    command_span: SourceSpan | None = None
    argument_span: SourceSpan | None = None
    command_path: tuple[str, ...] = ()
    entries: tuple[Any, ...] = ()
    group_path: tuple[str, ...] = ()
    available_subcommands: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BoundCommand:
    invocation: CommandInvocation
    values: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
