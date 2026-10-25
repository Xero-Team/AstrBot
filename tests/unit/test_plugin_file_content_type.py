import pytest

from astrbot.dashboard.services.plugin_file_ticket_service import (
    normalize_content_type,
    resolve_disposition,
)


@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain",
        "image/png",
        "image/svg+xml",
        "application/octet-stream",
        "application/vnd.example+json",
    ],
)
def test_normalize_content_type_accepts_single_media_type(content_type):
    assert normalize_content_type(content_type) == content_type


@pytest.mark.parametrize(
    "content_type",
    [
        "text/html; charset=utf-8",
        "text/html\r\nX-Injected: 1",
        "text/",
        "/html",
        "text",
        "text html",
        "",
    ],
)
def test_normalize_content_type_rejects_parameters_and_controls(content_type):
    with pytest.raises(ValueError):
        normalize_content_type(content_type)


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "application/xhtml+xml", "image/svg+xml", "text/xml"],
)
def test_document_media_is_forced_to_attachment(content_type):
    assert resolve_disposition(content_type, "inline") == "attachment"
    assert resolve_disposition(content_type, "attachment") == "attachment"


@pytest.mark.parametrize("content_type", ["image/png", "text/plain", "application/pdf"])
def test_safe_media_keeps_requested_disposition(content_type):
    assert resolve_disposition(content_type, "inline") == "inline"
    assert resolve_disposition(content_type, "attachment") == "attachment"
