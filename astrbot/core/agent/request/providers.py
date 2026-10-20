from typing import TYPE_CHECKING, TypeGuard

from astrbot import logger
from astrbot.core.agent.chat_model import ChatModel
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.provider_plan import ProviderPlan
from astrbot.core.platform.astr_message_event import AstrMessageEvent

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext

from .common import _set_llm_error_message
from .config import MainAgentBuildConfig


def _is_chat_model(value: object) -> TypeGuard[ChatModel]:
    """Check the complete chat capability needed by the main Agent path."""
    return (
        isinstance(getattr(value, "provider_config", None), dict)
        and callable(getattr(value, "get_model", None))
        and callable(getattr(value, "meta", None))
        and callable(getattr(value, "text_chat", None))
        and callable(getattr(value, "text_chat_stream", None))
    )


def _can_text_chat(value: object) -> bool:
    """Check the smaller capability needed by image-caption requests."""
    return callable(getattr(value, "text_chat", None))


def _select_provider(
    event: AstrMessageEvent,
    plugin_context: CoreExecutionContext,
    provider_id_override: str = "",
) -> ChatModel | None:
    """Select chat provider for the event.

    ``provider_id_override`` comes from persisted configuration (a BTW loop
    model) rather than from this request, so it is a preference: when it no
    longer resolves to a chat model, selection continues with the request's own
    choice and then the session/profile default. A provider chosen for this
    very request (``selected_provider``) still fails loudly, because the caller
    asked for that specific model.
    """
    if provider_id_override:
        provider = plugin_context.get_provider_by_id(provider_id_override)
        if provider is not None and _is_chat_model(provider):
            return provider
        logger.warning(
            "配置的对话模型 `%s` 不可用（未加载或类型不是对话模型），"
            "本次请求改用请求或会话选择的对话模型。",
            provider_id_override,
        )

    sel_provider = event.get_extra("selected_provider")
    if sel_provider and isinstance(sel_provider, str):
        provider = plugin_context.get_provider_by_id(sel_provider)
        if provider is None:
            logger.error("未找到指定的提供商: %s。", sel_provider)
            _set_llm_error_message(
                event,
                "providerNotFound",
                provider=sel_provider,
            )
            return None
        if not _is_chat_model(provider):
            logger.error(
                "选择的提供商类型无效(%s)，跳过 LLM 请求处理。", type(provider)
            )
            _set_llm_error_message(
                event,
                "invalidProviderType",
                provider_type=type(provider).__name__,
            )
            return None
        return provider
    try:
        locale = event.get_extra("locale")
        locale_kwargs = {"locale": locale} if isinstance(locale, str) else {}
        return plugin_context.get_using_provider(
            umo=event.unified_msg_origin, **locale_kwargs
        )
    except ValueError as exc:
        logger.error("Error occurred while selecting provider: %s", exc)
        _set_llm_error_message(event, "requestFailed", detail=str(exc))
        return None


def _get_compress_provider(
    config: MainAgentBuildConfig,
    plugin_context: CoreExecutionContext,
    event: AstrMessageEvent | None = None,
) -> ChatModel | None:
    if config.context_limit_reached_strategy != "llm_compress":
        return None
    if config.llm_compress_provider_id:
        provider = plugin_context.get_provider_by_id(config.llm_compress_provider_id)
        if provider and _is_chat_model(provider):
            return provider
        logger.warning(
            "指定的上下文压缩模型 %s 不可用",
            config.llm_compress_provider_id,
        )
    # fallback: use current chat provider for this session
    if event:
        try:
            return plugin_context.get_using_provider(umo=event.unified_msg_origin)
        except ValueError:
            pass
    return None


def _get_fallback_chat_providers(
    provider: ChatModel,
    plugin_context: CoreExecutionContext,
    fallback_ids: list[str],
) -> list[ChatModel]:
    if not isinstance(fallback_ids, list):
        logger.warning(
            "Agent Runner fallback_provider_ids is not a list, skip fallback providers."
        )
        return []

    provider_id = str(provider.provider_config.get("id", ""))
    seen_provider_ids: set[str] = {provider_id} if provider_id else set()
    fallbacks: list[ChatModel] = []

    for fallback_id in fallback_ids:
        if not isinstance(fallback_id, str) or not fallback_id:
            continue
        if fallback_id in seen_provider_ids:
            continue
        fallback_provider = plugin_context.get_provider_by_id(fallback_id)
        if fallback_provider is None:
            logger.warning("Fallback chat provider `%s` not found, skip.", fallback_id)
            continue
        if not _is_chat_model(fallback_provider):
            logger.warning(
                "Fallback chat provider `%s` is invalid type: %s, skip.",
                fallback_id,
                type(fallback_provider),
            )
            continue
        fallbacks.append(fallback_provider)
        seen_provider_ids.add(fallback_id)
    return fallbacks


def _provider_supports_modality(provider: ChatModel, modality: str) -> bool:
    modalities = provider.provider_config.get("modalities", None)
    return isinstance(modalities, list) and modality in modalities


def _select_image_chat_provider(
    provider: ChatModel,
    req: ProviderRequest,
    fallback_providers: list[ChatModel],
) -> ChatModel:
    if not req.image_urls or _provider_supports_modality(provider, "image"):
        return provider

    provider_id = provider.provider_config.get("id", "<unknown>")
    for fallback_provider in fallback_providers:
        if not _provider_supports_modality(fallback_provider, "image"):
            continue
        fallback_id = fallback_provider.provider_config.get("id", "<unknown>")
        logger.warning(
            "Chat provider %s does not support image input, switching this request to fallback provider %s.",
            provider_id,
            fallback_id,
        )
        return fallback_provider

    logger.warning(
        "Chat provider %s does not support image input and no image-capable fallback provider is available.",
        provider_id,
    )
    return provider


def _select_request_provider(
    provider: ChatModel,
    req: ProviderRequest,
    plugin_context: CoreExecutionContext,
    config: MainAgentBuildConfig,
) -> tuple[ChatModel, list[ChatModel]]:
    """Select an image-capable provider and preserve ordered fallbacks."""
    plan = ProviderPlan.from_candidates(
        provider,
        _get_fallback_chat_providers(
            provider, plugin_context, config.fallback_provider_ids
        ),
    )
    selected = _select_image_chat_provider(provider, req, list(plan.fallbacks))
    if selected is provider:
        return provider, list(plan.fallbacks)
    if req.model:
        req.model = None
    plan = plan.with_primary(selected)
    return plan.primary, list(plan.fallbacks)
