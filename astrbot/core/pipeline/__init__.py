"""Pipeline package exports.

This module intentionally avoids eager imports of all pipeline stage modules to
prevent import-time cycles. Stage classes remain available via lazy attribute
resolution for backward compatibility.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from astrbot.core.message.message_event_result import (
    EventResultType,
    MessageEventResult,
)

if TYPE_CHECKING:
    from .admission_check.stage import AdmissionCheckStage
    from .content_safety_check.stage import ContentSafetyCheckStage
    from .group_message_history.stage import GroupMessageHistoryStage
    from .preprocess_stage.stage import PreProcessStage
    from .process_stage.stage import ProcessStage
    from .rate_limit_check.stage import RateLimitStage
    from .respond.stage import RespondStage
    from .result_decorate.stage import ResultDecorateStage
    from .session_status_check.stage import SessionStatusCheckStage
    from .waking_check.stage import WakingCheckStage

_LAZY_EXPORTS = {
    "AdmissionCheckStage": (
        "astrbot.core.pipeline.admission_check.stage",
        "AdmissionCheckStage",
    ),
    "ContentSafetyCheckStage": (
        "astrbot.core.pipeline.content_safety_check.stage",
        "ContentSafetyCheckStage",
    ),
    "GroupMessageHistoryStage": (
        "astrbot.core.pipeline.group_message_history.stage",
        "GroupMessageHistoryStage",
    ),
    "PreProcessStage": (
        "astrbot.core.pipeline.preprocess_stage.stage",
        "PreProcessStage",
    ),
    "ProcessStage": (
        "astrbot.core.pipeline.process_stage.stage",
        "ProcessStage",
    ),
    "RateLimitStage": (
        "astrbot.core.pipeline.rate_limit_check.stage",
        "RateLimitStage",
    ),
    "RespondStage": (
        "astrbot.core.pipeline.respond.stage",
        "RespondStage",
    ),
    "ResultDecorateStage": (
        "astrbot.core.pipeline.result_decorate.stage",
        "ResultDecorateStage",
    ),
    "SessionStatusCheckStage": (
        "astrbot.core.pipeline.session_status_check.stage",
        "SessionStatusCheckStage",
    ),
    "WakingCheckStage": (
        "astrbot.core.pipeline.waking_check.stage",
        "WakingCheckStage",
    ),
}

__all__ = [
    "AdmissionCheckStage",
    "ContentSafetyCheckStage",
    "EventResultType",
    "GroupMessageHistoryStage",
    "MessageEventResult",
    "PreProcessStage",
    "ProcessStage",
    "RateLimitStage",
    "RespondStage",
    "ResultDecorateStage",
    "SessionStatusCheckStage",
    "STAGES_ORDER",
    "WakingCheckStage",
]


def __getattr__(name: str) -> Any:
    if name == "STAGES_ORDER":
        from .bootstrap import builtin_stage_order

        value = builtin_stage_order()
        globals()[name] = value
        return value
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_path)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
