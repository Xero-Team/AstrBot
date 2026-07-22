import enum
import os
import subprocess
from dataclasses import FrozenInstanceError
from typing import Annotated, Literal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from astrbot.api.command import CommandError, CommandSyntaxError, parse_arguments
from astrbot.api.event.filter import GreedyStr, option
from astrbot.core.command import (
    CommandBinder,
    CommandCatalog,
    CommandCatalogRegistration,
    CommandCatalogStore,
    CommandDiagnostic,
    CommandEngine,
    CommandErrorCode,
    CommandGroupRegistration,
    CommandLexer,
    CommandResolutionKind,
    SourceSpan,
    compile_command_schema,
    render_diagnostic,
)


def _error_code(source: str) -> CommandErrorCode:
    with pytest.raises(CommandSyntaxError) as caught:
        parse_arguments(source)
    return caught.value.diagnostic.code


@pytest.mark.parametrize(
    ("source", "argv"),
    [
        ("alpha \"beta gamma\" delta'42'", ("alpha", "beta gamma", "delta42")),
        ("ab\"cd\"'ef'", ("abcdef",)),
        ("\"\" ''", ("", "")),
        (r"escaped\ value say\"hi\" tail\\", ("escaped value", 'say"hi"', "tail\\")),
        ("one\\\ntwo", ("onetwo",)),
        ("\\\n", ()),
        ('"a\\qb"', (r"a\qb",)),
        ('"a\\$b\\`c\\\\d\\"e"', ('a$b`c\\d"e',)),
        (r'"C:\Users\bot"', (r"C:\Users\bot",)),
        ("你好 '世界🌍'", ("你好", "世界🌍")),
        ("a\u00a0b", ("a\u00a0b",)),
        (
            r"\$HOME \`date\` \~ \*.txt \#tag \|",
            ("$HOME", "`date`", "~", "*.txt", "#tag", "|"),
        ),
        ("'$HOME' \"a|b\"", ("$HOME", "a|b")),
    ],
)
def test_lexer_golden(source: str, argv: tuple[str, ...]) -> None:
    assert parse_arguments(source).argv == argv


def test_lexer_preserves_precise_word_and_fragment_spans() -> None:
    invocation = parse_arguments("ab\"cd\" 'ef'")

    assert invocation.words[0].span == SourceSpan(0, 6)
    assert invocation.words[1].span == SourceSpan(7, 11)
    assert tuple(fragment.span for fragment in invocation.words[0].fragments) == (
        SourceSpan(0, 2),
        SourceSpan(2, 6),
    )


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("$HOME", CommandErrorCode.UNSUPPORTED_PARAMETER_EXPANSION),
        ("$'x'", CommandErrorCode.UNSUPPORTED_DOLLAR_SINGLE_QUOTE),
        ("$((1))", CommandErrorCode.UNSUPPORTED_ARITHMETIC_EXPANSION),
        ("$(date)", CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION),
        ("`date`", CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION),
        ("~", CommandErrorCode.UNSUPPORTED_TILDE_EXPANSION),
        ("*.txt", CommandErrorCode.UNSUPPORTED_PATHNAME_EXPANSION),
        ("a?", CommandErrorCode.UNSUPPORTED_PATHNAME_EXPANSION),
        ("[ab]", CommandErrorCode.UNSUPPORTED_PATHNAME_EXPANSION),
        ("a|b", CommandErrorCode.UNSUPPORTED_OPERATOR),
        ("a&b", CommandErrorCode.UNSUPPORTED_OPERATOR),
        ("a;b", CommandErrorCode.UNSUPPORTED_OPERATOR),
        ("<x", CommandErrorCode.UNSUPPORTED_OPERATOR),
        (">x", CommandErrorCode.UNSUPPORTED_OPERATOR),
        ("(x)", CommandErrorCode.UNSUPPORTED_OPERATOR),
        ("# comment", CommandErrorCode.UNSUPPORTED_COMMENT),
        ("a\nb", CommandErrorCode.UNSUPPORTED_COMMAND_SEPARATOR),
        ("a\0b", CommandErrorCode.NUL_CHARACTER),
        ("unfinished\\", CommandErrorCode.DANGLING_ESCAPE),
        ("'unfinished", CommandErrorCode.UNCLOSED_SINGLE_QUOTE),
        ('"unfinished', CommandErrorCode.UNCLOSED_DOUBLE_QUOTE),
        ('"$HOME"', CommandErrorCode.UNSUPPORTED_PARAMETER_EXPANSION),
        ('"`date`"', CommandErrorCode.UNSUPPORTED_COMMAND_SUBSTITUTION),
    ],
)
def test_lexer_rejects_unsupported_posix_constructs(
    source: str, code: CommandErrorCode
) -> None:
    assert _error_code(source) is code


def test_lexer_reports_exact_error_span() -> None:
    with pytest.raises(CommandSyntaxError) as caught:
        parse_arguments("alpha $HOME")

    assert caught.value.diagnostic.span == SourceSpan(6, 7)


def test_lexer_resource_limits_are_errors_not_truncation() -> None:
    with pytest.raises(CommandSyntaxError) as source_error:
        CommandLexer(max_source_length=3).lex("four")
    with pytest.raises(CommandSyntaxError) as word_error:
        CommandLexer(max_words=1).lex("one two")
    with pytest.raises(CommandSyntaxError) as fragment_error:
        CommandLexer(max_fragments=1).lex("a'b'")

    assert source_error.value.diagnostic.code is CommandErrorCode.SOURCE_TOO_LONG
    assert word_error.value.diagnostic.code is CommandErrorCode.TOO_MANY_WORDS
    assert fragment_error.value.diagnostic.code is CommandErrorCode.TOO_MANY_FRAGMENTS


@given(st.text(max_size=2048))
@settings(max_examples=150, deadline=500)
def test_arbitrary_unicode_terminates_with_linear_output(source: str) -> None:
    try:
        invocation = parse_arguments(source)
    except CommandError:
        return
    assert len(invocation.words) <= len(source) + 1
    assert sum(len(word.fragments) for word in invocation.words) <= len(source) + 1


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


@given(
    st.lists(
        st.text(alphabet=st.characters(blacklist_characters="\0"), max_size=40),
        max_size=20,
    )
)
def test_quote_round_trip(values: list[str]) -> None:
    source = " ".join(_single_quote(value) for value in values)
    assert parse_arguments(source).argv == tuple(values)


@given(st.text(alphabet=st.characters(blacklist_characters="\0"), max_size=100))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_successful_lexing_does_not_perform_io(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("lexer attempted I/O")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)

    assert parse_arguments(_single_quote(value)).argv == (value,)


def test_parse_results_are_immutable() -> None:
    invocation = parse_arguments("alpha")
    with pytest.raises(FrozenInstanceError):
        invocation.source = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        invocation.words[0].value = "changed"  # type: ignore[misc]


def test_diagnostic_is_serializable_and_renders_wide_unicode_caret() -> None:
    diagnostic = CommandDiagnostic(
        CommandErrorCode.UNKNOWN_OPTION,
        SourceSpan(3, 6),
        {"option": "--x"},
    )

    assert diagnostic.to_dict() == {
        "code": "binding.unknown_option",
        "category": "binding",
        "span": {"start": 3, "end": 6},
        "params": {"option": "--x"},
        "hint_code": None,
    }
    rendered = render_diagnostic(diagnostic, "你 --x", "en-US")
    assert "Unknown option" in rendered
    assert rendered.splitlines()[-1].startswith("   ")


class Mode(enum.Enum):
    FAST = "fast"
    SAFE = "safe"


class NumericMode(enum.Enum):
    OFF = -1
    ON = 1


class RatioMode(enum.Enum):
    HALF = 0.5
    FULL = 1.0


def test_binder_contains_custom_enum_conversion_failures() -> None:
    secret = "api_key=super-secret https://internal.example/command"

    class ExplosiveMode(enum.StrEnum):
        SAFE = "safe"

        @classmethod
        def _missing_(cls, value: object):
            raise RuntimeError(secret)

    async def handler(self, event, mode: ExplosiveMode) -> None: ...

    with pytest.raises(CommandError) as caught:
        _bind(handler, "invalid")

    assert caught.value.diagnostic.code is CommandErrorCode.INVALID_ARGUMENT
    assert secret not in str(caught.value)


def _bind(handler, source: str):
    schema = compile_command_schema(handler)
    invocation = parse_arguments(source)
    return dict(CommandBinder().bind(schema, invocation).values)


def test_binder_supports_scalar_enum_literal_optional_and_defaults() -> None:
    async def handler(
        self,
        event,
        name: str,
        count: int,
        ratio: float,
        enabled: bool,
        mode: Mode,
        level: Literal["low", "high"],
        note: str | None = None,
    ) -> None: ...

    assert _bind(handler, "demo 3 1.5 yes fast high") == {
        "name": "demo",
        "count": 3,
        "ratio": 1.5,
        "enabled": True,
        "mode": Mode.FAST,
        "level": "high",
        "note": None,
    }


def test_binder_converts_numeric_enum_values_and_negative_positionals() -> None:
    async def handler(
        self,
        event,
        mode: NumericMode,
        ratio: RatioMode,
    ) -> None: ...

    assert _bind(handler, "-1 0.5") == {
        "mode": NumericMode.OFF,
        "ratio": RatioMode.HALF,
    }


def test_binder_supports_options_anywhere_inline_values_and_terminator() -> None:
    async def handler(
        self,
        event,
        name: str,
        page: Annotated[int | None, option("--page", "-p")] = None,
        force: Annotated[bool, option("--force", "-f")] = False,
    ) -> None: ...

    assert _bind(handler, "--page=2 alice --force") == {
        "name": "alice",
        "page": 2,
        "force": True,
    }
    assert _bind(handler, "--force false bob -p 3") == {
        "name": "bob",
        "page": 3,
        "force": False,
    }
    assert _bind(handler, "-- --force") == {
        "name": "--force",
        "page": None,
        "force": False,
    }


def test_binder_accepts_negative_numeric_positionals() -> None:
    async def handler(self, event, count: int, ratio: float) -> None: ...

    assert _bind(handler, "-1 -2.5") == {"count": -1, "ratio": -2.5}


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("--pages 2 alice", CommandErrorCode.UNKNOWN_OPTION),
        ("--page 1 --page 2 alice", CommandErrorCode.DUPLICATE_OPTION),
        ("alice --page", CommandErrorCode.MISSING_OPTION_VALUE),
        ("", CommandErrorCode.MISSING_ARGUMENT),
        ("alice extra", CommandErrorCode.TOO_MANY_ARGUMENTS),
        ("alice --page nope", CommandErrorCode.INVALID_ARGUMENT),
    ],
)
def test_binder_reports_distinct_errors(source: str, code: CommandErrorCode) -> None:
    async def handler(
        self,
        event,
        name: str,
        page: Annotated[int | None, option("--page", "-p")] = None,
    ) -> None: ...

    with pytest.raises(CommandError) as caught:
        _bind(handler, source)
    assert caught.value.diagnostic.code is code


def test_required_and_default_greedy_string() -> None:
    async def required(self, event, text: GreedyStr) -> None: ...

    async def defaulted(self, event, text: GreedyStr = "") -> None: ...

    with pytest.raises(CommandError) as caught:
        _bind(required, "")
    assert caught.value.diagnostic.code is CommandErrorCode.MISSING_ARGUMENT
    assert _bind(defaulted, "") == {"text": ""}
    assert _bind(required, "one 'two three'") == {"text": "one two three"}


@pytest.mark.parametrize(
    "annotation",
    [str | int | None, list[str], dict[str, str]],
)
def test_schema_rejects_unsupported_types(annotation) -> None:
    async def handler(self, event, value: annotation) -> None: ...

    with pytest.raises(CommandError) as caught:
        compile_command_schema(handler)
    assert caught.value.diagnostic.code is CommandErrorCode.UNSUPPORTED_SIGNATURE


@pytest.mark.parametrize(
    "enum_type",
    [
        enum.Enum("EmptyMode", {}),
        enum.Enum("MixedMode", {"TEXT": "text", "NUMBER": 1}),
        enum.Enum("TupleMode", {"PAIR": (1, 2)}),
    ],
)
def test_schema_rejects_unsupported_enum_values(enum_type: type[enum.Enum]) -> None:
    async def handler(self, event, value: enum_type) -> None: ...

    with pytest.raises(CommandError) as caught:
        compile_command_schema(handler)
    assert caught.value.diagnostic.code is CommandErrorCode.UNSUPPORTED_SIGNATURE


@pytest.mark.parametrize("name", ["-", "--", "---bad", "--bad=name", "--bad name"])
def test_option_rejects_names_that_conflict_with_orbit_syntax(name: str) -> None:
    with pytest.raises(ValueError, match="invalid option name"):
        option(name)


def test_diagnostic_renders_multiline_crlf_tabs_and_combining_marks() -> None:
    source = "first\r\n\t你e\u0301 --bad\r\nlast"
    start = source.index("--bad")
    diagnostic = CommandDiagnostic(
        CommandErrorCode.UNKNOWN_OPTION,
        SourceSpan(start, start + len("--bad")),
        {"option": "--bad"},
    )

    lines = render_diagnostic(diagnostic, source, "en-US").splitlines()
    assert lines[-2] == "    你e\u0301 --bad"
    assert lines[-1] == " " * 8 + "^" * 5


def _catalog() -> CommandCatalog:
    async def root(self, event, value: str = "") -> None: ...

    async def nested(self, event, count: int = 0) -> None: ...

    return CommandCatalog(
        (
            CommandCatalogRegistration(
                "root", root, compile_command_schema(root), (("name",), ("n",))
            ),
            CommandCatalogRegistration(
                "nested",
                nested,
                compile_command_schema(nested),
                (("plugin", "get"), ("p", "g")),
            ),
        ),
        (CommandGroupRegistration((("plugin",), ("p",))),),
    )


def test_catalog_resolves_roots_aliases_groups_and_longest_match() -> None:
    engine = CommandEngine(_catalog())
    root = engine.resolve("n value")
    nested = engine.resolve("plugin get 3")

    assert root.resolution.command_path == ("n",)
    assert root.invocation and root.invocation.argv == ("value",)
    assert nested.resolution.command_path == ("plugin", "get")
    assert nested.invocation and nested.invocation.argv == ("3",)


def test_catalog_group_and_unknown_resolution_behavior() -> None:
    engine = CommandEngine(_catalog())
    with pytest.raises(CommandError) as incomplete:
        engine.resolve("plugin")
    with pytest.raises(CommandError) as unknown_subcommand:
        engine.resolve("plugin remove")

    assert incomplete.value.diagnostic.code is CommandErrorCode.INCOMPLETE_COMMAND_GROUP
    assert (
        unknown_subcommand.value.diagnostic.code is CommandErrorCode.UNKNOWN_SUBCOMMAND
    )
    assert (
        engine.resolve("unknown $HOME").resolution.kind
        is CommandResolutionKind.UNKNOWN_ROOT
    )
    assert "└── get" in render_diagnostic(
        incomplete.value.diagnostic,
        "plugin",
        "en-US",
    )


def test_engine_enforces_source_limit_only_after_command_match() -> None:
    engine = CommandEngine(_catalog(), lexer=CommandLexer(max_source_length=8))

    with pytest.raises(CommandSyntaxError) as caught:
        engine.resolve("name long")
    assert caught.value.diagnostic.code is CommandErrorCode.SOURCE_TOO_LONG
    assert (
        engine.resolve("unknown text that is longer").resolution.kind
        is CommandResolutionKind.UNKNOWN_ROOT
    )


def test_engine_enforces_syntax_and_resource_limits_for_recognized_groups() -> None:
    engine = CommandEngine(_catalog())
    limited_engine = CommandEngine(_catalog(), lexer=CommandLexer(max_source_length=8))

    with pytest.raises(CommandSyntaxError) as newline_error:
        engine.resolve("plugin\n")
    with pytest.raises(CommandSyntaxError) as length_error:
        limited_engine.resolve("plugin   ")

    assert (
        newline_error.value.diagnostic.code
        is CommandErrorCode.UNSUPPORTED_COMMAND_SEPARATOR
    )
    assert length_error.value.diagnostic.code is CommandErrorCode.SOURCE_TOO_LONG


def test_catalog_store_replaces_snapshot_without_mutating_readers() -> None:
    original = _catalog()
    store = CommandCatalogStore(original)
    empty = CommandCatalog()

    observed = store.snapshot
    store.replace(empty)

    assert observed.resolve("name value").kind is CommandResolutionKind.MATCHED
    assert (
        store.snapshot.resolve("name value").kind is CommandResolutionKind.UNKNOWN_ROOT
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX differential check requires /bin/sh")
@pytest.mark.parametrize(
    "source",
    ["alpha beta", "'a b' c", 'ab"cd"', r"escaped\ value", '"C:\\Users\\bot"'],
)
def test_safe_subset_matches_posix_shell_argv(source: str) -> None:
    script = f"set -- {source}; printf '%s\\0' \"$@\""
    completed = subprocess.run(
        ["/bin/sh", "-c", script], check=True, capture_output=True
    )
    expected = tuple(completed.stdout.rstrip(b"\0").decode().split("\0"))
    assert parse_arguments(source).argv == expected
