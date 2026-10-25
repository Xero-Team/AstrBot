"""Tests for local Computer Use configuration change logging."""

from unittest.mock import patch

from astrbot.dashboard.services.config_service import _log_computer_config_changes


class TestLogComputerConfigChanges:
    """Test config change detection and logging."""

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_logs_runtime_change(self, mock_logger) -> None:
        old = {"provider_settings": {"computer_use_runtime": "none"}}
        new = {"provider_settings": {"computer_use_runtime": "local"}}

        _log_computer_config_changes(old, new)

        call_args = [str(c) for c in mock_logger.info.call_args_list]
        assert any(
            "computer_use_runtime" in c and "none" in c and "local" in c
            for c in call_args
        )

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_no_log_when_runtime_unchanged(self, mock_logger) -> None:
        old = {"provider_settings": {"computer_use_runtime": "local"}}
        new = {"provider_settings": {"computer_use_runtime": "local"}}

        _log_computer_config_changes(old, new)

        mock_logger.info.assert_not_called()

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_logs_local_permission_change(self, mock_logger) -> None:
        old = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "member": {"filesystem_scope": "none"}
                }
            }
        }
        new = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "member": {"filesystem_scope": "workspace"}
                }
            }
        }

        _log_computer_config_changes(old, new)

        args = mock_logger.info.call_args.args
        assert args[0] == (
            "[Computer] Config changed: local_permissions.%s.%s %s -> %s"
        )
        assert args[1:5] == ("member", "filesystem_scope", "none", "workspace")

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_handles_missing_provider_settings(self, mock_logger) -> None:
        _log_computer_config_changes(
            {}, {"provider_settings": {"computer_use_runtime": "local"}}
        )

        call_args_str = str(mock_logger.info.call_args_list)
        assert "computer_use_runtime" in call_args_str
