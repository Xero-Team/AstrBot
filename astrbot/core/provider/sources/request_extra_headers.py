from typing import Any


def extra_headers_kwargs(headers: dict[str, str] | None) -> dict[str, Any]:
    return {"extra_headers": headers} if headers else {}
