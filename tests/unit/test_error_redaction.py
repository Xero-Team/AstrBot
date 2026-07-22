from astrbot.core.utils.error_redaction import redact_sensitive_text


def test_redact_sensitive_text_removes_credentials_urls_and_absolute_paths():
    text = (
        "api_key=top-secret "
        "Bearer bearer-secret "
        "password=super-secret "
        "https://internal.example.test/private/config "
        "C:\\runtime\\secrets\\config.json "
        "/srv/astrbot/data/config.json"
    )

    redacted = redact_sensitive_text(text)

    for sensitive_value in (
        "top-secret",
        "bearer-secret",
        "super-secret",
        "internal.example.test",
        "C:\\runtime\\secrets\\config.json",
        "/srv/astrbot/data/config.json",
    ):
        assert sensitive_value not in redacted
