from types import SimpleNamespace
from unittest.mock import MagicMock

from astrbot.core.utils import webhook_utils


def test_log_webhook_info_uses_v1_platform_webhook_path(monkeypatch):
    monkeypatch.setattr(
        webhook_utils,
        "astrbot_config",
        SimpleNamespace(
            get=lambda key, default=None: {
                "callback_api_base": "https://example.com",
                "dashboard": {"port": 6185, "ssl": {"enable": False}},
            }.get(key, default)
        ),
    )
    mock_logger = MagicMock()
    monkeypatch.setattr(webhook_utils, "logger", mock_logger)

    webhook_utils.log_webhook_info("demo", "hook-123")

    logged = mock_logger.info.call_args.args[0]
    assert "/api/v1/webhooks/platforms/hook-123" in logged
    assert "/api/platform/webhook/" not in logged
