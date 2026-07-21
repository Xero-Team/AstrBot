import enum
import inspect
import types
import typing
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .diagnostics import CommandDiagnostic, CommandError, CommandErrorCode
from .models import SourceSpan


class GreedyStr(str):
    """Consume all remaining positional command arguments."""


@dataclass(frozen=True, slots=True)
class CommandOptionSpec:
    names: tuple[str, ...]


def option(*option_names: str) -> CommandOptionSpec:
    """Declare option names for an ``Annotated`` command parameter."""

    if not option_names:
        raise ValueError("option() requires at least one name")
    names: list[str] = []
    for name in option_names:
        if not name.startswith("-") or name in {"-", "--"} or name.startswith("---"):
            raise ValueError(f"invalid option name: {name}")
        if "=" in name or any(char in name for char in " \t\r\n"):
            raise ValueError(f"invalid option name: {name}")
        if name in names:
            raise ValueError(f"duplicate option name: {name}")
        names.append(name)
    return CommandOptionSpec(tuple(names))


@dataclass(frozen=True, slots=True)
class CommandParamSpec:
    name: str
    value_type: Any
    display_type: str
    default: Any = inspect.Parameter.empty
    option: CommandOptionSpec | None = None
    optional: bool = False
    literals: tuple[Any, ...] = ()
    input_type: type = str

    @property
    def has_default(self) -> bool:
        return self.default is not inspect.Parameter.empty

    @property
    def is_required(self) -> bool:
        return not self.has_default

    @property
    def is_greedy(self) -> bool:
        return self.value_type is GreedyStr

    @property
    def is_bool(self) -> bool:
        return self.value_type is bool

    @property
    def is_numeric(self) -> bool:
        return self.input_type in (int, float)


@dataclass(frozen=True, slots=True)
class CommandSchema:
    params: tuple[CommandParamSpec, ...]
    option_map: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "option_map", MappingProxyType(dict(self.option_map)))

    def option_index(self, name: str) -> int | None:
        return self.option_map.get(name)

    @property
    def option_names(self) -> tuple[str, ...]:
        return tuple(self.option_map)

    def format_params(self) -> str:
        parts: list[str] = []
        for param in self.params:
            option_display = f"[{'/'.join(param.option.names)}]" if param.option else ""
            text = f"{param.name}{option_display}({param.display_type})"
            if param.has_default:
                text += f"={param.default}"
            parts.append(text)
        return ",".join(parts)


def _schema_error(reason: str) -> CommandError:
    return CommandError(
        CommandDiagnostic(
            CommandErrorCode.UNSUPPORTED_SIGNATURE,
            SourceSpan(0, 0),
            {"reason": reason},
        )
    )


def _unwrap_annotated(annotation: Any) -> tuple[Any, CommandOptionSpec | None]:
    if typing.get_origin(annotation) is not typing.Annotated:
        return annotation, None
    annotation, *metadata = typing.get_args(annotation)
    options = [item for item in metadata if isinstance(item, CommandOptionSpec)]
    if len(options) > 1:
        raise _schema_error("a parameter cannot declare multiple option() values")
    return annotation, options[0] if options else None


def _compile_type(
    name: str, annotation: Any, default: Any
) -> tuple[Any, str, bool, tuple[Any, ...], type]:
    optional = False
    literals: tuple[Any, ...] = ()
    if annotation is inspect.Parameter.empty:
        value_type = (
            str
            if default is inspect.Parameter.empty or default is None
            else type(default)
        )
    else:
        value_type = annotation

    origin = typing.get_origin(value_type)
    if origin in (typing.Union, types.UnionType):
        args = typing.get_args(value_type)
        non_none = tuple(item for item in args if item is not type(None))
        if len(args) != 2 or len(non_none) != 1:
            raise _schema_error(f"parameter '{name}' only supports a T | None union")
        value_type = non_none[0]
        optional = True
        origin = typing.get_origin(value_type)

    if origin is typing.Literal:
        literals = typing.get_args(value_type)
        if not literals or any(
            type(item) not in (str, int, float, bool) for item in literals
        ):
            raise _schema_error(f"parameter '{name}' has unsupported Literal values")
        literal_types = {type(item) for item in literals}
        if len(literal_types) != 1:
            raise _schema_error(f"parameter '{name}' must use one Literal value type")
        value_type = type(literals[0])
        display = "Literal[" + ", ".join(repr(item) for item in literals) + "]"
        return value_type, display, optional, literals, value_type

    if value_type in (str, int, float, bool, GreedyStr):
        display = value_type.__name__
        input_type = str if value_type is GreedyStr else value_type
    elif inspect.isclass(value_type) and issubclass(value_type, enum.Enum):
        members = tuple(value_type)
        if not members:
            raise _schema_error(f"parameter '{name}' cannot use an empty Enum")
        member_types = {type(member.value) for member in members}
        if len(member_types) != 1:
            raise _schema_error(f"parameter '{name}' must use one Enum value type")
        input_type = member_types.pop()
        if input_type not in (str, int, float, bool):
            raise _schema_error(f"parameter '{name}' has unsupported Enum values")
        display = value_type.__name__
    else:
        raise _schema_error(
            f"parameter '{name}' has unsupported annotation {value_type!r}"
        )
    if optional:
        display += " | None"
    return value_type, display, optional, literals, input_type


def compile_command_schema(handler: Any) -> CommandSchema:
    """Compile and validate a handler signature during registration."""

    signature = inspect.signature(handler)
    parameters = tuple(signature.parameters.values())
    if len(parameters) < 2:
        raise _schema_error("a command handler must accept self and event")
    try:
        hints = typing.get_type_hints(handler, include_extras=True)
    except (NameError, TypeError) as exc:
        raise _schema_error(f"type annotations could not be resolved: {exc}") from exc

    compiled: list[CommandParamSpec] = []
    option_map: list[tuple[str, int]] = []
    seen_options: set[str] = set()
    seen_greedy = False
    for parameter in parameters[2:]:
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            raise _schema_error(
                f"parameter '{parameter.name}' cannot be variadic or keyword-only"
            )
        annotation = hints.get(parameter.name, parameter.annotation)
        annotation, option_spec = _unwrap_annotated(annotation)
        value_type, display_type, optional, literals, input_type = _compile_type(
            parameter.name, annotation, parameter.default
        )
        param = CommandParamSpec(
            parameter.name,
            value_type,
            display_type,
            parameter.default,
            option_spec,
            optional,
            literals,
            input_type,
        )
        if param.is_greedy and option_spec:
            raise _schema_error(
                f"parameter '{parameter.name}' cannot combine GreedyStr and option()"
            )
        if param.is_greedy:
            seen_greedy = True
        elif seen_greedy and option_spec is None:
            raise _schema_error("GreedyStr must be the final positional parameter")
        if option_spec:
            for option_name in option_spec.names:
                if option_name in seen_options:
                    raise _schema_error(f"duplicate option name '{option_name}'")
                seen_options.add(option_name)
                option_map.append((option_name, len(compiled)))
        compiled.append(param)
    return CommandSchema(tuple(compiled), dict(option_map))
