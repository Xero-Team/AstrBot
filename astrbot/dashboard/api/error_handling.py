from typing import Any

from fastapi.responses import JSONResponse

from astrbot.core.utils.error_redaction import safe_error, sanitize_error_text
from astrbot.dashboard.responses import INTERNAL_SERVER_ERROR_MESSAGE, error


def safe_service_message(message: object) -> str:
    """Render a service error message without internal detail.

    Business messages raised by dashboard services are intentionally shown to
    callers, but credentials, URLs, absolute paths, and control characters are
    removed first so a service message cannot leak internal detail.
    """
    return sanitize_error_text(message)


def service_error_response(exc: Exception) -> dict[str, Any]:
    """Return a typed service error envelope with a safely rendered message."""
    return error(safe_service_message(exc))


def internal_error_response(
    logger: Any,
    context: str,
    exc: Exception,
) -> JSONResponse:
    """Log an unexpected API failure safely and return a stable envelope."""
    logger.error("%s: %s", context, safe_error("", exc))
    return JSONResponse(
        error(INTERNAL_SERVER_ERROR_MESSAGE),
        status_code=500,
    )
