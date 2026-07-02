import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.error_redaction import safe_error

MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT = 30.0
MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT = 4
MODEL_LOOKUP_MAX_CONCURRENCY_UPPER_BOUND = 16
MODEL_LIST_CACHE_TTL_KEY = "model_list_cache_ttl_seconds"
MODEL_LOOKUP_MAX_CONCURRENCY_KEY = "model_lookup_max_concurrency"
MODEL_CACHE_MAX_ENTRIES = 512


@dataclass(frozen=True)
class _ModelLookupConfig:
    umo: str | None
    cache_ttl_seconds: float
    max_concurrency: int


class _ModelCache:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str | None], tuple[float, list[str]]] = {}

    def get(self, provider_id: str, umo: str | None, ttl: float) -> list[str] | None:
        if ttl <= 0:
            return None
        entry = self._store.get((provider_id, umo))
        if not entry:
            return None
        timestamp, models = entry
        if time.monotonic() - timestamp > ttl:
            self._store.pop((provider_id, umo), None)
            return None
        return models

    def set(
        self,
        provider_id: str,
        umo: str | None,
        models: list[str],
        ttl: float,
    ) -> None:
        if ttl <= 0:
            return
        self._store[(provider_id, umo)] = (time.monotonic(), list(models))
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        if len(self._store) <= MODEL_CACHE_MAX_ENTRIES:
            return
        overflow = len(self._store) - MODEL_CACHE_MAX_ENTRIES
        for key, _ in sorted(self._store.items(), key=lambda item: item[1][0])[
            :overflow
        ]:
            self._store.pop(key, None)

    def invalidate(
        self,
        provider_id: str | None = None,
        *,
        umo: str | None = None,
    ) -> None:
        if provider_id is None:
            self._store.clear()
            return
        if umo is not None:
            self._store.pop((provider_id, umo), None)
            return
        stale_keys = [
            cache_key for cache_key in self._store if cache_key[0] == provider_id
        ]
        for cache_key in stale_keys:
            self._store.pop(cache_key, None)


class ProviderCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context
        self._model_cache = _ModelCache()
        self._register_provider_change_hook()

    def _register_provider_change_hook(self) -> None:
        register_change_hook = getattr(
            self.context.provider_manager,
            "register_provider_change_hook",
            None,
        )
        if callable(register_change_hook):
            register_change_hook(self._on_provider_manager_changed)

    def invalidate_provider_models_cache(
        self,
        provider_id: str | None = None,
        *,
        umo: str | None = None,
    ) -> None:
        self._model_cache.invalidate(provider_id, umo=umo)

    def _on_provider_manager_changed(
        self,
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None,
    ) -> None:
        if provider_type == ProviderType.CHAT_COMPLETION:
            self.invalidate_provider_models_cache(provider_id, umo=umo)

    def _get_provider_settings(self, umo: str | None) -> dict:
        if not umo:
            return {}
        try:
            return self.context.get_config(umo).get("provider_settings", {}) or {}
        except Exception as exc:
            logger.debug("Failed to read provider settings, using defaults: %s", exc)
            return {}

    def _get_model_cache_ttl(self, umo: str | None) -> float:
        raw = self._get_provider_settings(umo).get(
            MODEL_LIST_CACHE_TTL_KEY,
            MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT,
        )
        try:
            return max(float(raw), 0.0)
        except Exception as exc:
            logger.debug("Invalid %s value %r: %s", MODEL_LIST_CACHE_TTL_KEY, raw, exc)
            return MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT

    def _get_model_lookup_concurrency(self, umo: str | None) -> int:
        raw = self._get_provider_settings(umo).get(
            MODEL_LOOKUP_MAX_CONCURRENCY_KEY,
            MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT,
        )
        try:
            value = int(raw)
        except Exception as exc:
            logger.debug(
                "Invalid %s value %r: %s",
                MODEL_LOOKUP_MAX_CONCURRENCY_KEY,
                raw,
                exc,
            )
            value = MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT
        return min(max(value, 1), MODEL_LOOKUP_MAX_CONCURRENCY_UPPER_BOUND)

    def _get_model_lookup_config(self, umo: str | None) -> _ModelLookupConfig:
        return _ModelLookupConfig(
            umo=umo,
            cache_ttl_seconds=self._get_model_cache_ttl(umo),
            max_concurrency=self._get_model_lookup_concurrency(umo),
        )

    def _resolve_model_name(
        self,
        model_name: str,
        models: Sequence[str],
    ) -> str | None:
        requested = model_name.strip()
        if not requested:
            return None

        requested_norm = requested.casefold()
        for candidate in models:
            if candidate == requested or candidate.casefold() == requested_norm:
                return candidate

        for candidate in models:
            cand_norm = candidate.casefold()
            if cand_norm.endswith(f"/{requested_norm}") or cand_norm.endswith(
                f":{requested_norm}"
            ):
                return candidate

        return None

    def _apply_model(
        self,
        provider: Provider,
        model_name: str,
        *,
        umo: str | None = None,
    ) -> str:
        provider.set_model(model_name)
        self.invalidate_provider_models_cache(provider.meta().id, umo=umo)
        return (
            f"✅ Switched model successfully.\n"
            f"Provider: {provider.meta().id}\n"
            f"Model: {provider.get_model()}"
        )

    async def _get_provider_models(
        self,
        provider: Provider,
        *,
        config: _ModelLookupConfig,
        use_cache: bool = True,
    ) -> list[str]:
        provider_id = provider.meta().id
        if use_cache:
            cached = self._model_cache.get(
                provider_id,
                config.umo,
                config.cache_ttl_seconds,
            )
            if cached is not None:
                return cached

        models = list(await provider.get_models())
        if use_cache:
            self._model_cache.set(
                provider_id,
                config.umo,
                models,
                config.cache_ttl_seconds,
            )
        return models

    async def _get_models_or_reply_error(
        self,
        event: AstrMessageEvent,
        provider: Provider,
        config: _ModelLookupConfig,
        *,
        error_prefix: str,
        disable_t2i: bool = False,
        warning_log: str | None = None,
    ) -> list[str] | None:
        try:
            return await self._get_provider_models(provider, config=config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if warning_log is not None:
                logger.warning(warning_log, provider.meta().id, safe_error("", exc))
            result = MessageEventResult().message(safe_error(error_prefix, exc))
            if disable_t2i:
                result = result.use_t2i(False)
            event.set_result(result)
            return None

    async def _find_provider_for_model(
        self,
        model_name: str,
        *,
        exclude_provider_id: str | None = None,
        config: _ModelLookupConfig,
        use_cache: bool = True,
    ) -> tuple[Provider | None, str | None]:
        all_providers: list[Provider] = []
        for provider in self.context.get_all_providers():
            if provider.meta().provider_type != ProviderType.CHAT_COMPLETION:
                continue
            if (
                exclude_provider_id is not None
                and provider.meta().id == exclude_provider_id
            ):
                continue
            all_providers.append(provider)
        if not all_providers:
            return None, None

        semaphore = asyncio.Semaphore(config.max_concurrency)

        async def fetch_models(
            provider: Provider,
        ) -> tuple[Provider, list[str] | None, str | None]:
            async with semaphore:
                try:
                    models = await self._get_provider_models(
                        provider,
                        config=config,
                        use_cache=use_cache,
                    )
                    return provider, models, None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    err = safe_error("", exc)
                    logger.debug(
                        "Failed to fetch model list from %s while looking for %s: %s",
                        provider.meta().id,
                        model_name,
                        err,
                    )
                    return provider, None, err

        results = await asyncio.gather(
            *(fetch_models(provider) for provider in all_providers)
        )
        failed_provider_errors: list[tuple[str, str]] = []
        for provider, models, err in results:
            if err is not None:
                failed_provider_errors.append((provider.meta().id, err))
                continue
            if models is None:
                continue

            matched_model_name = self._resolve_model_name(model_name, models)
            if matched_model_name is not None:
                return provider, matched_model_name

        if failed_provider_errors and len(failed_provider_errors) == len(all_providers):
            logger.error(
                "All providers failed while looking up model %s: %s",
                model_name,
                ",".join(provider_id for provider_id, _ in failed_provider_errors),
            )
        return None, None

    def _log_reachability_failure(
        self,
        provider,
        provider_capability_type: ProviderType | None,
        err_code: str,
        err_reason: str,
    ) -> None:
        meta = provider.meta()
        logger.warning(
            "Provider reachability check failed: id=%s type=%s code=%s reason=%s",
            meta.id,
            provider_capability_type.name if provider_capability_type else "unknown",
            err_code,
            err_reason,
        )

    async def _test_provider_capability(self, provider):
        meta = provider.meta()
        provider_capability_type = meta.provider_type

        try:
            await provider.test()
            return True, None, None
        except Exception as exc:
            err_code = "TEST_FAILED"
            err_reason = safe_error("", exc)
            self._log_reachability_failure(
                provider,
                provider_capability_type,
                err_code,
                err_reason,
            )
            return False, err_code, err_reason

    async def _build_provider_display_data(
        self,
        providers,
        provider_type: str,
        reachability_check_enabled: bool,
    ) -> list[dict]:
        if not providers:
            return []

        if reachability_check_enabled:
            check_results = await asyncio.gather(
                *[self._test_provider_capability(provider) for provider in providers],
                return_exceptions=True,
            )
        else:
            check_results = [None for _ in providers]

        display_data = []
        for provider, reachable in zip(providers, check_results):
            meta = provider.meta()
            id_ = meta.id
            error_code = None

            if isinstance(reachable, asyncio.CancelledError):
                raise reachable
            if isinstance(reachable, Exception):
                self._log_reachability_failure(
                    provider,
                    None,
                    reachable.__class__.__name__,
                    safe_error("", reachable),
                )
                reachable_flag = False
                error_code = reachable.__class__.__name__
            elif isinstance(reachable, tuple):
                reachable_flag, error_code, _ = reachable
            else:
                reachable_flag = reachable

            if provider_type == "llm":
                info = f"{id_} ({meta.model})"
            else:
                info = f"{id_}"

            if reachable_flag is True:
                mark = " ✅"
            elif reachable_flag is False:
                if error_code:
                    mark = f" ❌(errcode: {error_code})"
                else:
                    mark = " ❌"
            else:
                mark = ""

            display_data.append(
                {
                    "info": info,
                    "mark": mark,
                    "provider": provider,
                },
            )

        return display_data

    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ) -> None:
        """View or switch the current provider."""
        umo = event.unified_msg_origin
        cfg = self.context.get_config(umo).get("provider_settings", {})
        reachability_check_enabled = cfg.get("reachability_check", True)

        if idx is None:
            parts = ["## LLM Providers\n"]

            llms = list(self.context.get_all_providers())
            ttss = self.context.get_all_tts_providers()
            stts = self.context.get_all_stt_providers()

            if reachability_check_enabled and (llms or ttss or stts):
                await event.send(
                    MessageEventResult().message("👀 Testing provider reachability...")
                )

            llm_data, tts_data, stt_data = await asyncio.gather(
                self._build_provider_display_data(
                    llms,
                    "llm",
                    reachability_check_enabled,
                ),
                self._build_provider_display_data(
                    ttss,
                    "tts",
                    reachability_check_enabled,
                ),
                self._build_provider_display_data(
                    stts,
                    "stt",
                    reachability_check_enabled,
                ),
            )

            provider_using = self.context.get_using_provider(umo=umo)
            for index, data in enumerate(llm_data):
                line = f"{index + 1}. {data['info']}{data['mark']}"
                if (
                    provider_using
                    and provider_using.meta().id == data["provider"].meta().id
                ):
                    line += " 👈"
                parts.append(line + "\n")

            if tts_data:
                parts.append("\n## TTS Providers\n")
                tts_using = self.context.get_using_tts_provider(umo=umo)
                for index, data in enumerate(tts_data):
                    line = f"{index + 1}. {data['info']}{data['mark']}"
                    if tts_using and tts_using.meta().id == data["provider"].meta().id:
                        line += " 👈"
                    parts.append(line + "\n")

            if stt_data:
                parts.append("\n## STT Providers\n")
                stt_using = self.context.get_using_stt_provider(umo=umo)
                for index, data in enumerate(stt_data):
                    line = f"{index + 1}. {data['info']}{data['mark']}"
                    if stt_using and stt_using.meta().id == data["provider"].meta().id:
                        line += " 👈"
                    parts.append(line + "\n")

            parts.append("\nUse /provider <idx> to switch LLM providers.")
            ret = "".join(parts)

            if ttss:
                ret += "\nUse /provider tts <idx> to switch TTS providers."
            if stts:
                ret += "\nUse /provider stt <idx> to switch STT providers."

            event.set_result(MessageEventResult().message(ret))
        elif idx == "tts":
            if idx2 is None:
                event.set_result(
                    MessageEventResult().message("Please enter the index."),
                )
                return
            if idx2 > len(self.context.get_all_tts_providers()) or idx2 < 1:
                event.set_result(
                    MessageEventResult().message("❌ Invalid provider index."),
                )
                return
            provider = self.context.get_all_tts_providers()[idx2 - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.TEXT_TO_SPEECH,
                umo=umo,
            )
            event.set_result(
                MessageEventResult().message(f"✅ Successfully switched to {id_}."),
            )
        elif idx == "stt":
            if idx2 is None:
                event.set_result(
                    MessageEventResult().message("Please enter the index."),
                )
                return
            if idx2 > len(self.context.get_all_stt_providers()) or idx2 < 1:
                event.set_result(
                    MessageEventResult().message("❌ Invalid provider index."),
                )
                return
            provider = self.context.get_all_stt_providers()[idx2 - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.SPEECH_TO_TEXT,
                umo=umo,
            )
            event.set_result(
                MessageEventResult().message(f"✅ Successfully switched to {id_}."),
            )
        elif isinstance(idx, int):
            if idx > len(self.context.get_all_providers()) or idx < 1:
                event.set_result(
                    MessageEventResult().message("❌ Invalid provider index."),
                )
                return
            provider = self.context.get_all_providers()[idx - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            event.set_result(
                MessageEventResult().message(f"✅ Successfully switched to {id_}."),
            )
        else:
            event.set_result(MessageEventResult().message("❌ Invalid parameter."))

    async def _switch_model_by_name(
        self,
        event: AstrMessageEvent,
        model_name: str,
        provider: Provider,
    ) -> None:
        model_name = model_name.strip()
        if not model_name:
            event.set_result(
                MessageEventResult().message("Model name cannot be empty."),
            )
            return

        umo = event.unified_msg_origin
        config = self._get_model_lookup_config(umo)
        current_provider_id = provider.meta().id

        models = await self._get_models_or_reply_error(
            event,
            provider,
            config,
            error_prefix="Failed to fetch models from the current provider: ",
            warning_log="Failed to fetch models from provider %s: %s",
        )
        if models is None:
            return

        matched_model_name = self._resolve_model_name(model_name, models)
        if matched_model_name is not None:
            event.set_result(
                MessageEventResult().message(
                    self._apply_model(provider, matched_model_name, umo=umo),
                ),
            )
            return

        (
            target_provider,
            matched_target_model_name,
        ) = await self._find_provider_for_model(
            model_name,
            exclude_provider_id=current_provider_id,
            config=config,
        )
        if target_provider is None or matched_target_model_name is None:
            event.set_result(
                MessageEventResult().message(
                    f"❌ Model `{model_name}` was not found in any configured provider.",
                ),
            )
            return

        target_id = target_provider.meta().id
        try:
            await self.context.provider_manager.set_provider(
                provider_id=target_id,
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            self._apply_model(target_provider, matched_target_model_name, umo=umo)
            event.set_result(
                MessageEventResult().message(
                    f"✅ Switched provider to {target_id} and selected model {matched_target_model_name}.",
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            event.set_result(
                MessageEventResult().message(
                    safe_error("Failed to switch provider and model: ", exc),
                ),
            )

    async def model_ls(
        self,
        event: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ) -> None:
        """View or switch the current chat model."""
        provider = self.context.get_using_provider(event.unified_msg_origin)
        if not provider:
            event.set_result(
                MessageEventResult().message(
                    "❌ Cannot find any LLM provider. Configure one first.",
                ),
            )
            return

        config = self._get_model_lookup_config(event.unified_msg_origin)
        if idx_or_name is None:
            models = await self._get_models_or_reply_error(
                event,
                provider,
                config,
                error_prefix="Failed to fetch model list: ",
                disable_t2i=True,
            )
            if models is None:
                return

            parts = ["Available models for the current provider:"]
            for index, model in enumerate(models, 1):
                parts.append(f"\n{index}. {model}")
            current_model = provider.get_model() or "(empty)"
            parts.append(f"\nCurrent model: {current_model}")
            parts.append(
                "\nUse /model <name|index> to switch models. Model names can be resolved across configured providers.",
            )
            event.set_result(
                MessageEventResult().message("".join(parts)).use_t2i(False),
            )
            return

        if isinstance(idx_or_name, int):
            models = await self._get_models_or_reply_error(
                event,
                provider,
                config,
                error_prefix="Failed to fetch model list: ",
            )
            if models is None:
                return
            if idx_or_name < 1 or idx_or_name > len(models):
                event.set_result(
                    MessageEventResult().message("❌ Invalid model index."),
                )
                return

            try:
                new_model = models[idx_or_name - 1]
                event.set_result(
                    MessageEventResult().message(
                        self._apply_model(
                            provider,
                            new_model,
                            umo=event.unified_msg_origin,
                        ),
                    ),
                )
            except Exception as exc:
                event.set_result(
                    MessageEventResult().message(
                        safe_error("Failed to switch model: ", exc),
                    ),
                )
            return

        await self._switch_model_by_name(event, idx_or_name, provider)
