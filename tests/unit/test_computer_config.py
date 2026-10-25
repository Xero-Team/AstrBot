"""Tests for local Computer Use configuration change logging."""

import sys
from unittest.mock import patch

from astrbot.dashboard.services.config_service import (
    _log_computer_config_changes,
    _validate_local_permissions,
)


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

    @patch("astrbot.dashboard.services.config_service.logger")
    def test_logs_policy_shapes_without_rule_entries(self, mock_logger) -> None:
        old = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "admin": {
                        "network": {
                            "mode": "allowlist",
                            "allowed_domains": ["secret.internal.example"],
                        },
                        "filesystem": {
                            "deny_read": ["/home/operator/.ssh/id_ed25519"],
                        },
                    }
                }
            }
        }
        new = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "admin": {
                        "network": {
                            "mode": "allowlist",
                            "allowed_domains": [
                                "secret.internal.example",
                                "another.internal.example",
                            ],
                        },
                        "filesystem": {
                            "deny_read": [
                                "/home/operator/.ssh/id_ed25519",
                                "/home/operator/.ssh/id_rsa",
                            ],
                        },
                    }
                }
            }
        }

        _log_computer_config_changes(old, new)

        logged = str(mock_logger.info.call_args_list)
        assert "secret.internal.example" not in logged
        assert "id_ed25519" not in logged
        assert "allowed_domains" in logged
        assert "deny_read" in logged

    def test_validation_normalizes_nested_policy(self) -> None:
        data = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "member": {
                        "allow_execution": True,
                        "filesystem_scope": "workspace",
                        "network": {
                            "mode": "unrestricted",
                            "allowed_domains": ["stale.example"],
                            "denied_domains": ["blocked.example"],
                            "allow_private_network": True,
                            "allow_loopback": True,
                        },
                        "filesystem": {"deny_read": [], "deny_write": []},
                        "unix_sockets": {"mode": "allow_all", "allowed_paths": []},
                    }
                }
            }
        }
        errors: list[str] = []
        _validate_local_permissions(data, errors)
        assert errors == []
        policy = data["provider_settings"]["computer_use_local_permissions"]["member"]
        assert policy["network"]["allowed_domains"] == []
        assert policy["network"]["denied_domains"] == ["blocked.example"]

    def test_validation_rejects_unknown_keys_and_linux_socket_paths(
        self, tmp_path
    ) -> None:
        data = {
            "provider_settings": {
                "computer_use_local_permissions": {
                    "member": {
                        "allow_execution": True,
                        "filesystem_scope": "workspace",
                        "network": {"mode": "off", "unknown": True},
                        "filesystem": {"deny_read": []},
                        "unix_sockets": {
                            "mode": "deny",
                            "allowed_paths": [str(tmp_path / "api.sock")],
                        },
                        "allow_network": True,
                    }
                }
            }
        }
        errors: list[str] = []
        _validate_local_permissions(data, errors)
        joined = "\n".join(errors)
        assert "Unknown network policy key" in joined
        assert "Unknown Local permission key" in joined
        if sys.platform != "darwin":
            assert "supported only on macOS" in joined
