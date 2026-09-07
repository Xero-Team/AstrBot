import re

_SECRET_KEYS = (
    r"(?:api_?key|access_?token|auth_?token|refresh_?token|session_?id|secret|password)"
)

_JSON_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>(?P<kq>['\"]){_SECRET_KEYS}(?P=kq)\s*:\s*)(?P<vq>['\"])(?P<value>[^'\"]+)(?P=vq)"
)
_AUTH_JSON_FIELD_PATTERN = re.compile(
    r"(?i)(?P<prefix>(?P<kq>['\"])authorization(?P=kq)\s*:\s*)(?P<vq>['\"])bearer\s+[^'\"]+(?P=vq)"
)
_QUERY_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>{_SECRET_KEYS}\s*=\s*)(?P<value>[^&'\" ]+)"
)
_QUERY_PARAM_PATTERN = re.compile(
    r"(?i)(?P<prefix>[?&](?:api_?key|key|access_?token|auth_?token)=)(?P<value>[^&'\" ]+)"
)
_AUTH_HEADER_PATTERN = re.compile(
    r"(?i)(?P<prefix>\bauthorization\s*:\s*bearer\s+)(?P<token>[A-Za-z0-9._\-]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(?P<prefix>\bbearer\s+)(?P<token>[A-Za-z0-9._\-]+)")
_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")
_URL_PATTERN = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s'\"<>]+")
_DATA_URI_PATTERN = re.compile(r"(?i)\bdata:[a-z0-9.+-]+/[a-z0-9.+-]+[^\s'\"<>]*")
_WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/]|\\\\)[^\s'\"<>]+"
)
_UNIX_ABSOLUTE_PATH_PATTERN = re.compile(
    # Require at least one alphanumeric path component. This avoids treating
    # slash-prefixed ASCII-art fragments such as ``/_\`` and ``/__/`` as paths
    # while still redacting ordinary paths (including names beginning with `_`).
    r"(?<![A-Za-z0-9_])/(?=[A-Za-z0-9._~/-]*[A-Za-z0-9])[^\s'\"<>]+"
)


def _redact_json_field(match: re.Match[str]) -> str:
    quote = match.group("vq")
    return f"{match.group('prefix')}{quote}[REDACTED]{quote}"


def _redact_auth_json_field(match: re.Match[str]) -> str:
    quote = match.group("vq")
    return f"{match.group('prefix')}{quote}Bearer [REDACTED]{quote}"


def _redact_prefixed_value(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}[REDACTED]"


def _redact_bearer_token(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}[REDACTED]"


def _redact_json_like(text: str) -> str:
    text = _JSON_FIELD_PATTERN.sub(_redact_json_field, text)
    return _AUTH_JSON_FIELD_PATTERN.sub(_redact_auth_json_field, text)


def _redact_query_like(text: str) -> str:
    text = _QUERY_FIELD_PATTERN.sub(_redact_prefixed_value, text)
    return _QUERY_PARAM_PATTERN.sub(_redact_prefixed_value, text)


def _redact_tokens(text: str) -> str:
    text = _AUTH_HEADER_PATTERN.sub(_redact_bearer_token, text)
    text = _BEARER_PATTERN.sub(_redact_bearer_token, text)
    return _SK_PATTERN.sub("[REDACTED]", text)


def _redact_urls(text: str) -> str:
    text = _URL_PATTERN.sub("[REDACTED_URL]", text)
    return _DATA_URI_PATTERN.sub("[REDACTED_URL]", text)


def _redact_paths(text: str) -> str:
    text = _WINDOWS_ABSOLUTE_PATH_PATTERN.sub("[REDACTED_PATH]", text)
    return _UNIX_ABSOLUTE_PATH_PATTERN.sub("[REDACTED_PATH]", text)


def redact_sensitive_text(text: str, *, redact_paths: bool = True) -> str:
    """Redact credentials, tokens, URLs, and optionally filesystem paths.

    Args:
        text: Untrusted text that may contain secrets.
        redact_paths: When True, also replace absolute filesystem paths.

    Returns:
        Redacted text.
    """
    text = _redact_json_like(text)
    text = _redact_query_like(text)
    text = _redact_tokens(text)
    text = _redact_urls(text)
    if redact_paths:
        return _redact_paths(text)
    return text


def safe_error(
    prefix: str,
    error: Exception | BaseException | str,
    *,
    redact: bool = True,
) -> str:
    try:
        text = str(error)
    except Exception:
        try:
            text = repr(error)
        except Exception:
            text = "<unprintable error>"
    if redact:
        text = redact_sensitive_text(text)
    return prefix + text
