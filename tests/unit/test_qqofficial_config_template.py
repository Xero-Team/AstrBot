from astrbot.core.config.default import CONFIG_METADATA_2


def _platform_template(name: str) -> dict:
    templates = CONFIG_METADATA_2["platform_group"]["metadata"]["platform"][
        "config_template"
    ]
    return templates[name]


def test_qqofficial_templates_both_expose_use_markdown():
    websocket = _platform_template("QQ 官方机器人(Websocket, 推荐)")
    webhook = _platform_template("QQ 官方机器人(Webhook)")

    assert websocket["use_markdown"] is True
    assert webhook["use_markdown"] is True
