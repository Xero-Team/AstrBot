from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.dashboard.services.stat_service import StatServiceError
from tests.unit.dashboard.fastapi_v1_support import _jwt_headers


@pytest.mark.asyncio
async def test_pypi_index_routes_return_service_results(asgi_app, asgi_client):
    stats = SimpleNamespace(
        test_pypi_index_connection=AsyncMock(return_value={"latency": 12.5}),
        measure_pypi_index_speed=AsyncMock(
            return_value={"speed": 1.5, "bytes": 2048, "duration": 0.25},
        ),
    )
    asgi_app.state.services.stats = stats

    probed = await asgi_client.post(
        "/api/v1/stats/pypi-index/test",
        headers=_jwt_headers(),
        json={"index_url": "https://mirror.example/simple"},
    )
    assert probed.status_code == 200
    assert probed.json()["status"] == "ok"
    assert probed.json()["data"] == {"latency": 12.5}
    stats.test_pypi_index_connection.assert_awaited_once_with(
        "https://mirror.example/simple"
    )

    measured = await asgi_client.post(
        "/api/v1/stats/pypi-index/speed",
        headers=_jwt_headers(),
        json={"index_url": "https://mirror.example/simple"},
    )
    assert measured.status_code == 200
    assert measured.json()["data"] == {
        "speed": 1.5,
        "bytes": 2048,
        "duration": 0.25,
    }
    stats.measure_pypi_index_speed.assert_awaited_once_with(
        "https://mirror.example/simple"
    )


@pytest.mark.asyncio
async def test_pypi_index_routes_require_dashboard_auth(asgi_app, asgi_client):
    stats = SimpleNamespace(
        test_pypi_index_connection=AsyncMock(return_value={"latency": 1.0}),
        measure_pypi_index_speed=AsyncMock(return_value={"speed": 1.0}),
    )
    asgi_app.state.services.stats = stats

    anonymous = await asgi_client.post(
        "/api/v1/stats/pypi-index/test",
        json={"index_url": "https://mirror.example/simple"},
    )
    assert anonymous.status_code in {401, 403}
    stats.test_pypi_index_connection.assert_not_awaited()


@pytest.mark.asyncio
async def test_pypi_index_route_reports_service_errors(asgi_app, asgi_client):
    stats = SimpleNamespace(
        test_pypi_index_connection=AsyncMock(return_value={"latency": 1.0}),
        measure_pypi_index_speed=AsyncMock(
            side_effect=StatServiceError("镜像测速失败"),
        ),
    )
    asgi_app.state.services.stats = stats

    failed = await asgi_client.post(
        "/api/v1/stats/pypi-index/speed",
        headers=_jwt_headers(),
        json={"index_url": "https://mirror.example/simple"},
    )
    assert failed.status_code == 400
    assert failed.json()["status"] == "error"
    assert failed.json()["message"] == "镜像测速失败"
