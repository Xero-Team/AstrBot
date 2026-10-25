from pathlib import Path

from astrbot.core.utils.io import _safe_url_for_log

ROOT = Path(__file__).resolve().parents[2]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_safe_url_for_log_uses_hostname_without_userinfo():
    rendered = _safe_url_for_log(
        "https://user:password@internal.example:8443/private/file.bin?token=secret"
    )

    assert "user" not in rendered
    assert "password" not in rendered
    assert "internal.example" in rendered


def test_high_volume_logs_do_not_embed_raw_payloads():
    assert 'logger.info(f"Received Slack event: {event_data}")' not in _source(
        "astrbot/core/platform/sources/slack/client.py"
    )
    assert 'logger.info(f"解析成功: {msg}")' not in _source(
        "astrbot/core/platform/sources/wecom/wecom_adapter.py"
    )
    assert 'logger.info(f"abm: {abm}")' not in _source(
        "astrbot/core/platform/sources/wecom/wecom_adapter.py"
    )
    dify = _source("astrbot/core/agent/runners/dify/dify_api_client.py")
    assert 'logger.info(f"chat_messages payload: {payload}")' not in dify
    assert 'logger.info(f"workflow_run payload: {payload}")' not in dify


def test_agent_errors_are_redacted_or_generic():
    coze = _source("astrbot/core/agent/runners/coze/coze_agent_runner.py")
    assert 'f"Coze 请求失败：{str(e)}"' not in coze
    assert "safe_error" in coze
    context = _source("astrbot/core/pipeline/context_utils.py")
    assert "logger.error(traceback.format_exc())" not in context
    assert "redact_sensitive_text(traceback.format_exc())" in context
    mcp = _source("astrbot/core/tools/function_tool_manager.py")
    assert 'f"testing MCP server connection with config: {config}"' not in mcp
    assert "FunctionToolManager._log_safe_mcp_debug_config(config)" in mcp
