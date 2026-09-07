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


def test_redact_sensitive_text_can_keep_absolute_paths():
    text = (
        "Bearer bearer-secret "
        "https://internal.example.test/private/config "
        "/srv/astrbot/data/config.json"
    )

    redacted = redact_sensitive_text(text, redact_paths=False)

    assert "bearer-secret" not in redacted
    assert "internal.example.test" not in redacted
    assert "/srv/astrbot/data/config.json" in redacted


def test_redact_sensitive_text_redacts_data_uris():
    payload = "A" * 64
    redacted = redact_sensitive_text(f"failed data:image/gif;base64,{payload}")

    assert payload not in redacted
    assert "data:image" not in redacted
    assert "[REDACTED_URL]" in redacted


def test_redact_sensitive_text_redacts_parameterized_data_uris():
    payload = "B" * 32
    redacted = redact_sensitive_text(
        f"failed data:image/png;charset=utf-8;base64,{payload}"
    )

    assert payload not in redacted
    assert "[REDACTED_URL]" in redacted


def test_redact_sensitive_text_data_uri_pattern_is_linear():
    probe = "data:image/gif" + (";!" * 4000)
    redacted = redact_sensitive_text(f"failed {probe}")

    assert probe not in redacted
    assert "[REDACTED_URL]" in redacted


def test_redact_sensitive_text_does_not_corrupt_ascii_art():
    logo_fragment = r" /  /_\  \       \   \       |  |     |  |"

    assert redact_sensitive_text(logo_fragment) == logo_fragment
    assert redact_sensitive_text("/__user/config.json") == "[REDACTED_PATH]"
