import json

from astrbot.core.tools.registry import _evaluate_send_message_tool


def test_wecom_ai_bot_condition_does_not_echo_webhook_url():
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret"
    conditions = _evaluate_send_message_tool(
        {
            "platform": [
                {
                    "enable": True,
                    "type": "wecom_ai_bot",
                    "id": "wecom-main",
                    "msg_push_webhook_url": webhook,
                }
            ]
        }
    )

    rendered = json.dumps(conditions)
    assert "secret" not in rendered
    assert webhook not in rendered
    assert all(condition.get("actual") is None for condition in conditions)
