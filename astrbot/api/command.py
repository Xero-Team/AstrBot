"""Supported plugin API for deterministic command argument parsing."""

from astrbot.core.command.diagnostics import (
    CommandDiagnostic,
    CommandError,
    CommandSyntaxError,
)
from astrbot.core.command.lexer import parse_arguments
from astrbot.core.command.models import CommandInvocation, CommandWord

__all__ = [
    "CommandDiagnostic",
    "CommandError",
    "CommandInvocation",
    "CommandSyntaxError",
    "CommandWord",
    "parse_arguments",
]
