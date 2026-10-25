import re

_SECRET_KEY_BASE = r"(?:api[-_]?key|access[-_]?token|auth[-_]?token|refresh[-_]?token|session[-_]?id|secret|password|token|key)"  # noqa: S105
_SECRET_KEY_NAME = rf"(?:[A-Za-z0-9]+[_-])*{_SECRET_KEY_BASE}(?:[_-][A-Za-z0-9]+)*"
# A bare ``key`` is also an ordinary English word ("Missing key: username").
# Keep it for assignments, JSON fields, and query parameters, but require a
# qualified name before a colon so field-name prose is not over-redacted.
_COLON_SECRET_KEY_BASE = r"(?:api[-_]?key|access[-_]?token|auth[-_]?token|refresh[-_]?token|session[-_]?id|secret|password|token)"  # noqa: S105
_COLON_SECRET_KEY_NAME = (
    rf"(?:[A-Za-z0-9]+[_-])*{_COLON_SECRET_KEY_BASE}(?:[_-][A-Za-z0-9]+)*"
)

_JSON_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>(?P<kq>['\"]){_SECRET_KEY_NAME}(?P=kq)\s*:\s*)"
    r"(?P<vq>['\"])(?P<value>(?:\\.|(?!(?P=vq)).)*)(?P=vq)"
)
_AUTH_JSON_FIELD_PATTERN = re.compile(
    r"(?i)(?P<prefix>(?P<kq>['\"])[A-Za-z0-9_-]*authorization(?P=kq)\s*:\s*)"
    r"(?P<vq>['\"])(?P<scheme>[A-Za-z][A-Za-z0-9_-]*)\s+"
    r"(?P<value>(?:\\.|(?!(?P=vq)).)*)(?P=vq)"
)
_QUOTED_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>(?<![A-Za-z0-9]){_SECRET_KEY_NAME}\s*[:=]\s*)"
    r"(?P<vq>['\"])(?P<value>(?:\\.|(?!(?P=vq)).)*)(?P=vq)"
)
_COLON_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>(?<![A-Za-z0-9]){_COLON_SECRET_KEY_NAME}\s*:\s*)"
    r"(?P<value>(?!['\"])[^\s&]+)"
)
_QUERY_FIELD_PATTERN = re.compile(
    rf"(?i)(?P<prefix>(?<![A-Za-z0-9]){_SECRET_KEY_NAME}\s*=\s*)"
    r"(?P<value>(?!['\"])[^\s&]+)"
)
_QUERY_PARAM_PATTERN = re.compile(
    rf"(?i)(?P<prefix>[?&]{_SECRET_KEY_NAME}=)(?P<value>[^&\s]+)"
)
_AUTH_HEADER_PATTERN = re.compile(
    r"(?i)(?P<prefix>\bauthorization\s*:\s*)"
    r"(?P<scheme>[A-Za-z][A-Za-z0-9_-]*)\s+"
    r"(?P<token>[A-Za-z0-9._~+/=-]+)"
)
_AUTH_SCHEME_PATTERN = re.compile(
    r"(?i)(?P<prefix>\b(?:bearer|basic|digest|token)\s+)"
    r"(?P<token>[A-Za-z0-9._~+/=-]+)"
)
_SK_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
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
    return f"{match.group('prefix')}{quote}{match.group('scheme')} [REDACTED]{quote}"


def _redact_quoted_field(match: re.Match[str]) -> str:
    quote = match.group("vq")
    return f"{match.group('prefix')}{quote}[REDACTED]{quote}"


def _redact_prefixed_value(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}[REDACTED]"


def _redact_auth_value(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}{match.group('scheme')} [REDACTED]"


def _redact_auth_scheme_value(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}[REDACTED]"


def _redact_json_like(text: str) -> str:
    text = _JSON_FIELD_PATTERN.sub(_redact_json_field, text)
    return _AUTH_JSON_FIELD_PATTERN.sub(_redact_auth_json_field, text)


def _redact_query_like(text: str) -> str:
    text = _QUOTED_FIELD_PATTERN.sub(_redact_quoted_field, text)
    text = _COLON_FIELD_PATTERN.sub(_redact_prefixed_value, text)
    text = _QUERY_FIELD_PATTERN.sub(_redact_prefixed_value, text)
    return _QUERY_PARAM_PATTERN.sub(_redact_prefixed_value, text)


def _redact_tokens(text: str) -> str:
    text = _AUTH_HEADER_PATTERN.sub(_redact_auth_value, text)
    text = _AUTH_SCHEME_PATTERN.sub(_redact_auth_scheme_value, text)
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


def sanitize_error_text(message: object, *, redact_paths: bool = True) -> str:
    """Render an error message without secrets, paths, or control characters.

    Args:
        message: Value whose text should be rendered safely.
        redact_paths: Forwarded to :func:`redact_sensitive_text`.

    Returns:
        A single-line, redacted rendering of ``message``.
    """
    try:
        text = str(message)
    except Exception:
        try:
            text = repr(message)
        except Exception:
            text = "<unprintable error>"
    # Strip control characters first: an embedded newline such as
    # ``pass\nword: hunter2`` would otherwise reassemble into a secret the
    # redactor already passed over.
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    return redact_sensitive_text(text, redact_paths=redact_paths)
