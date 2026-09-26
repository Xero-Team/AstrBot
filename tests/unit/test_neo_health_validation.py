"""Regression tests for the Shipyard Neo health probe validation."""

from __future__ import annotations

from typing import Any

import pytest

from astrbot.dashboard.services.config_service import _validate_neo_connectivity

_CONNECTION_WARNING = "无法连接 Bay"


def _config(
    endpoint: str,
    *,
    runtime: str = "sandbox",
    booter: str = "shipyard_neo",
    token: str = "test-token",
) -> dict[str, Any]:
    return {
        "provider_settings": {
            "computer_use_runtime": runtime,
            "sandbox": {
                "booter": booter,
                "shipyard_neo_endpoint": endpoint,
                "shipyard_neo_access_token": token,
            },
        }
    }


@pytest.mark.asyncio
async def test_health_ok_uses_validated_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []

    async def fake_fetch_text(url: str, policy: Any, **_kwargs: Any):
        calls.append((url, policy))
        return 200, "ok", {}

    monkeypatch.setattr("astrbot.core.utils.outbound_http.fetch_text", fake_fetch_text)

    result = await _validate_neo_connectivity(_config("http://127.0.0.1:8114"))

    assert result is None
    assert calls
    url, policy = calls[0]
    assert url == "http://127.0.0.1:8114/health"
    assert policy.max_redirects == 0
    assert policy.allow_private_network is True


@pytest.mark.asyncio
async def test_non_200_reports_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_text(url: str, policy: Any, **_kwargs: Any):
        return 503, "down", {}

    monkeypatch.setattr("astrbot.core.utils.outbound_http.fetch_text", fake_fetch_text)

    result = await _validate_neo_connectivity(_config("http://127.0.0.1:8114"))

    assert result is not None
    assert "HTTP 503" in result


@pytest.mark.asyncio
async def test_fetch_failure_reports_connection_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def raising_fetch_text(url: str, policy: Any, **_kwargs: Any):
        from astrbot.core.utils.outbound_http import OutboundRequestError

        raise OutboundRequestError("blocked")

    monkeypatch.setattr(
        "astrbot.core.utils.outbound_http.fetch_text", raising_fetch_text
    )

    result = await _validate_neo_connectivity(_config("http://127.0.0.1:8114"))

    assert result is not None
    assert _CONNECTION_WARNING in result


@pytest.mark.asyncio
async def test_metadata_endpoint_is_never_fetched() -> None:
    result = await _validate_neo_connectivity(
        _config("http://169.254.169.254/latest/meta-data")
    )

    assert result is not None
    assert _CONNECTION_WARNING in result


@pytest.mark.asyncio
async def test_bad_scheme_and_credentials_are_rejected() -> None:
    for endpoint in (
        "file:///etc/passwd",
        "ftp://bay.example.com",
        "http://user:pass@127.0.0.1:8114",
    ):
        result = await _validate_neo_connectivity(_config(endpoint))
        assert result is not None
        assert _CONNECTION_WARNING in result


@pytest.mark.asyncio
async def test_skips_when_runtime_not_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_args: Any, **_kwargs: Any):
        raise AssertionError("fetch_text should not be called")

    monkeypatch.setattr("astrbot.core.utils.outbound_http.fetch_text", boom)

    assert (
        await _validate_neo_connectivity(
            _config("http://127.0.0.1:8114", runtime="none")
        )
        is None
    )
    assert (
        await _validate_neo_connectivity(_config("http://127.0.0.1:8114", booter="cua"))
        is None
    )


@pytest.mark.asyncio
async def test_missing_token_does_not_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_args: Any, **_kwargs: Any):
        raise AssertionError("fetch_text should not be called")

    monkeypatch.setattr("astrbot.core.utils.outbound_http.fetch_text", boom)
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client._discover_bay_credentials",
        lambda _endpoint: "",
    )

    result = await _validate_neo_connectivity(
        _config("http://127.0.0.1:8114", token="")
    )

    assert result is not None
    assert "API Key" in result or "访问令牌" in result
