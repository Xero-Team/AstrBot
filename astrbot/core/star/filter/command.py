from typing import TYPE_CHECKING

from astrbot.core.command.diagnostics import CommandError
from astrbot.core.command.schema import (
    CommandParamSpec,
    CommandSchema,
    compile_command_schema,
)
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..star_handler import StarHandlerMetadata
from . import HandlerFilter
from .custom_filter import CustomFilter

if TYPE_CHECKING:
    from .command_group import CommandGroupFilter


class CommandFilter(HandlerFilter):
    """Command registration metadata used by the command catalog."""

    def __init__(
        self,
        command_name: str,
        alias: set | None = None,
        handler_md: StarHandlerMetadata | None = None,
        parent_command_names: list[str] | None = None,
    ) -> None:
        self.command_name = command_name
        self.alias = alias if alias else set()
        self._original_command_name = command_name
        self.parent_command_names = parent_command_names or [""]
        self.parent_group: CommandGroupFilter | None = None
        self.custom_filter_list: list[CustomFilter] = []
        self.schema = CommandSchema((), {})
        self.handler_params: tuple[CommandParamSpec, ...] = ()
        self._cmpl_cmd_names: list[str] | None = None
        self.handler_md: StarHandlerMetadata | None = None
        if handler_md:
            self.init_handler_md(handler_md)

    def init_handler_md(self, handle_md: StarHandlerMetadata) -> None:
        self.handler_md = handle_md
        try:
            self.schema = compile_command_schema(handle_md.handler)
        except CommandError as exc:
            reason = exc.diagnostic.params.get("reason", exc.diagnostic.code.value)
            raise ValueError(
                "Invalid command handler "
                f"'{handle_md.handler_full_name}' in plugin "
                f"'{handle_md.handler_module_path}': {reason}"
            ) from exc
        self.handler_params = self.schema.params

    def get_handler_md(self) -> StarHandlerMetadata | None:
        return self.handler_md

    def add_custom_filter(self, custom_filter: CustomFilter) -> None:
        self.custom_filter_list.append(custom_filter)

    def custom_filter_ok(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        return all(item.filter(event, cfg) for item in self.custom_filter_list)

    def print_types(self) -> str:
        return self.schema.format_params()

    def format_invocation(
        self,
        command_name: str | None = None,
        include_aliases: bool = False,
    ) -> str:
        display_name = command_name or self.get_complete_command_names()[0]
        params_display = self.print_types()
        result = display_name
        if params_display:
            result += f" ({params_display})"
        if include_aliases and self.alias:
            result += f" [aliases: {', '.join(sorted(self.alias))}]"
        return result

    def get_complete_command_names(self) -> list[str]:
        if self.parent_group is not None:
            return [
                f"{parent} {name}"
                for name in [self.command_name, *sorted(self.alias)]
                for parent in self.parent_group.get_complete_command_names()
            ]
        if self._cmpl_cmd_names is None:
            self._cmpl_cmd_names = [
                f"{parent} {name}" if parent else name
                for name in [self.command_name, *sorted(self.alias)]
                for parent in self.parent_command_names
            ]
        return self._cmpl_cmd_names

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Check a match prepared by ``WakingCheckStage``.

        Command text parsing intentionally does not happen in filters.
        """

        if not event.is_at_or_wake_command or not self.handler_md:
            return False
        matched_ids = event.get_extra("command_handler_ids", default=())
        return (
            self.handler_md.handler_full_name in matched_ids
            and self.custom_filter_ok(event, cfg)
        )


__all__ = ["CommandFilter"]
