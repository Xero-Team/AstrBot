"""Locale-aware user-facing strings for the BTW work loop.

The work loop runs in core without a plugin context, so it resolves the
locale from the event extra/session the same way ``PluginContext._locale``
does, then looks the string up in these bundles. Missing locales fall back
to ``zh-CN``.
"""

LOCALES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "btw.work.started": "🔧 工作任务已开始处理。",
        "btw.work.status.pending": "工作任务正在排队。",
        "btw.work.status.running": "工作任务正在执行。",
        "btw.work.status.completed": "工作任务已完成。",
        "btw.work.status.failed": "工作任务执行失败。",
        "btw.work.status.cancelled": "工作任务已取消。",
        "btw.work.status.unconfirmed": "工作任务已结束，但结果投递未确认。",
    },
    "en-US": {
        "btw.work.started": "🔧 Work task started.",
        "btw.work.status.pending": "The work task is queued.",
        "btw.work.status.running": "The work task is running.",
        "btw.work.status.completed": "The work task is completed.",
        "btw.work.status.failed": "The work task failed.",
        "btw.work.status.cancelled": "The work task was cancelled.",
        "btw.work.status.unconfirmed": (
            "The work task ended, but its result delivery is unconfirmed."
        ),
    },
}

_FALLBACK_LOCALE = "zh-CN"


def resolve_event_locale(event) -> str:
    """Return the locale for an event (extra first, then the stored session)."""
    getter = getattr(event, "get_extra", None)
    if callable(getter):
        try:
            extra = getter("locale")
        except Exception:  # noqa: BLE001
            extra = None
        if extra:
            return str(extra)
    return _FALLBACK_LOCALE


def text(locale: str, key: str) -> str:
    """Return one BTW string for a locale, falling back to zh-CN then key."""
    bundle = LOCALES.get(locale) or LOCALES[_FALLBACK_LOCALE]
    value = bundle.get(key)
    if value is None:
        value = LOCALES[_FALLBACK_LOCALE].get(key, key)
    return value
