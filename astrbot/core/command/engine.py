from dataclasses import dataclass

from .binder import CommandBinder
from .catalog import CommandCatalog, CommandCatalogEntry
from .diagnostics import (
    CommandDiagnostic,
    CommandError,
    CommandErrorCode,
    CommandSyntaxError,
)
from .lexer import CommandLexer
from .models import (
    BoundCommand,
    CommandInvocation,
    CommandResolution,
    CommandResolutionKind,
    SourceSpan,
)

type _CommandTree = dict[str, _CommandTree]


def _format_subcommand_tree(paths: tuple[str, ...]) -> str:
    tree: _CommandTree = {}
    for path in paths:
        node = tree
        for part in path.split(" "):
            node = node.setdefault(part, {})

    lines: list[str] = []

    def append_children(node: _CommandTree, prefix: str) -> None:
        children = sorted(node.items())
        for index, (name, descendants) in enumerate(children):
            last = index == len(children) - 1
            lines.append(f"{prefix}{'└──' if last else '├──'} {name}")
            append_children(descendants, prefix + ("    " if last else "│   "))

    append_children(tree, "")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ResolvedCommand:
    resolution: CommandResolution
    invocation: CommandInvocation | None = None


class CommandEngine:
    """Resolve command framing, lex arguments once, and bind handlers."""

    def __init__(
        self,
        catalog: CommandCatalog,
        *,
        lexer: CommandLexer | None = None,
        binder: CommandBinder | None = None,
    ) -> None:
        self.catalog = catalog
        self.lexer = lexer or CommandLexer()
        self.binder = binder or CommandBinder()

    def resolve(self, source: str) -> ResolvedCommand:
        resolution = self.catalog.resolve(source)
        if resolution.kind is not CommandResolutionKind.UNKNOWN_ROOT:
            self._enforce_source_limit(source)
        if resolution.kind is CommandResolutionKind.MATCHED:
            assert resolution.argument_span is not None
            argument_source = source[resolution.argument_span.start :]
            parsed = self.lexer.lex(
                argument_source, offset=resolution.argument_span.start
            )
            invocation = CommandInvocation(
                source,
                parsed.words,
                resolution.command_span,
                resolution.argument_span,
            )
            return ResolvedCommand(resolution, invocation)
        if resolution.kind is CommandResolutionKind.INCOMPLETE_GROUP:
            assert resolution.command_span is not None
            self.lexer.lex(
                source[resolution.command_span.end :],
                offset=resolution.command_span.end,
            )
            command = " ".join(resolution.group_path)
            raise CommandError(
                CommandDiagnostic(
                    CommandErrorCode.INCOMPLETE_COMMAND_GROUP,
                    resolution.command_span or SourceSpan(0, len(source)),
                    {
                        "command": command,
                        "available": _format_subcommand_tree(
                            resolution.available_subcommands
                        ),
                    },
                )
            )
        if resolution.kind is CommandResolutionKind.UNKNOWN_SUBCOMMAND:
            command = " ".join(resolution.group_path)
            subcommand = resolution.command_path[-1]
            raise CommandError(
                CommandDiagnostic(
                    CommandErrorCode.UNKNOWN_SUBCOMMAND,
                    resolution.command_span or SourceSpan(0, len(source)),
                    {
                        "command": command,
                        "subcommand": subcommand,
                        "available": _format_subcommand_tree(
                            resolution.available_subcommands
                        ),
                    },
                )
            )
        return ResolvedCommand(resolution)

    def _enforce_source_limit(self, source: str) -> None:
        if len(source) > self.lexer.max_source_length:
            raise CommandSyntaxError(
                CommandDiagnostic(
                    CommandErrorCode.SOURCE_TOO_LONG,
                    SourceSpan(0, len(source)),
                    {"limit": self.lexer.max_source_length},
                )
            )

    def bind(
        self, entry: CommandCatalogEntry, resolved: ResolvedCommand
    ) -> BoundCommand:
        if resolved.invocation is None:
            raise ValueError("cannot bind an unmatched command")
        return self.binder.bind(entry.schema, resolved.invocation)
