from astrbot import __version__

DEFAULT_USER_AGENT = f"astrbot/{__version__}"


def build_provider_headers(custom_headers: object = None) -> dict[str, str]:
    """Build provider headers with an overridable AstrBot user agent.

    Args:
        custom_headers: Optional header mapping from provider configuration.

    Returns:
        A new header dictionary with string values and one User-Agent header.
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if isinstance(custom_headers, dict):
        for name, value in custom_headers.items():
            name, value = str(name), str(value)
            if name.lower() == "user-agent":
                if value.strip():
                    headers["User-Agent"] = value
            else:
                headers[name] = value
    return headers


def drop_sdk_user_agent(client: object) -> None:
    """Drop the SDK's extra lowercase User-Agent when the client exposes it.

    Args:
        client: A Gemini SDK client or test double. Missing private attributes
            are ignored so constructor tests can stub the client.
    """
    api_client = getattr(client, "_api_client", None)
    http_options = getattr(api_client, "_http_options", None)
    headers = getattr(http_options, "headers", None)
    pop = getattr(headers, "pop", None)
    if callable(pop):
        pop("user-agent", None)
