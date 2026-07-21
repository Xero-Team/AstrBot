from .binder import CommandBinder
from .catalog import (
    CommandCatalog,
    CommandCatalogEntry,
    CommandCatalogRegistration,
    CommandCatalogStore,
    CommandGroupRegistration,
    build_command_catalog,
)
from .diagnostics import (
    CommandDiagnostic,
    CommandError,
    CommandErrorCategory,
    CommandErrorCode,
    CommandHintCode,
    CommandSyntaxError,
    render_diagnostic,
)
from .engine import CommandEngine, ResolvedCommand
from .lexer import CommandLexer, parse_arguments
from .models import (
    BoundCommand,
    CommandInvocation,
    CommandResolution,
    CommandResolutionKind,
    CommandWord,
    SourceSpan,
    WordFragment,
    WordFragmentKind,
)
from .schema import (
    CommandOptionSpec,
    CommandParamSpec,
    CommandSchema,
    GreedyStr,
    compile_command_schema,
    option,
)

__all__ = [
    "BoundCommand",
    "CommandBinder",
    "CommandCatalog",
    "CommandCatalogEntry",
    "CommandCatalogRegistration",
    "CommandCatalogStore",
    "CommandDiagnostic",
    "CommandEngine",
    "CommandError",
    "CommandErrorCategory",
    "CommandErrorCode",
    "CommandGroupRegistration",
    "CommandHintCode",
    "CommandInvocation",
    "CommandLexer",
    "CommandOptionSpec",
    "CommandParamSpec",
    "CommandResolution",
    "CommandResolutionKind",
    "CommandSchema",
    "CommandSyntaxError",
    "CommandWord",
    "GreedyStr",
    "ResolvedCommand",
    "SourceSpan",
    "WordFragment",
    "WordFragmentKind",
    "build_command_catalog",
    "compile_command_schema",
    "option",
    "parse_arguments",
    "render_diagnostic",
]
