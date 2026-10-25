from types import SimpleNamespace

import pytest

from astrbot.core.provider.sources import request_retry
from astrbot.core.utils import network_utils

SECRET_TEXT = (
    "api_key=secret-key Bearer bearer-token password=dashboard-password "
    "https://internal.example/path?token=secret-token"
)


class RecordingLogger:
    def __init__(self):
        self.calls = []

    def error(self, *args):
        self.calls.append(args)

    def warning(self, *args):
        self.calls.append(args)


def test_connection_failure_log_redacts_proxy_and_error(monkeypatch):
    recorder = RecordingLogger()
    monkeypatch.setattr(network_utils, "logger", recorder)

    network_utils.log_connection_failure(
        "OpenAI",
        RuntimeError(SECRET_TEXT),
        "http://proxy-user:proxy-pass@proxy.example:8080",
    )

    rendered = " ".join(str(arg) for arg in recorder.calls[0])
    for value in (
        "proxy-user",
        "proxy-pass",
        "secret-key",
        "bearer-token",
        "dashboard-password",
        "internal.example",
    ):
        assert value not in rendered


def test_retry_log_redacts_provider_error(monkeypatch):
    recorder = RecordingLogger()
    monkeypatch.setattr(request_retry, "logger", recorder)
    retry_state = SimpleNamespace(
        outcome=SimpleNamespace(exception=lambda: RuntimeError(SECRET_TEXT)),
        attempt_number=0,
    )

    request_retry._log_retry("Gemini", retry_state, 3)

    rendered = " ".join(str(arg) for arg in recorder.calls[0])
    for value in (
        "secret-key",
        "bearer-token",
        "dashboard-password",
        "internal.example",
    ):
        assert value not in rendered
