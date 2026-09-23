from typing import TypedDict


class Personality(TypedDict):
    """LLM 人格类。

    在 v4.0.0 版本及之后，推荐使用 ``astrbot.core.db.po.Persona``。
    """

    prompt: str
    name: str
    begin_dialogs: list[str]
    tools: list[str] | None
    """工具列表。None 表示使用所有工具，空列表表示不使用任何工具"""
    skills: list[str] | None
    """Skills 列表。None 表示使用所有 Skills，空列表表示不使用任何 Skills"""
    custom_error_message: str | None
    """可选的人格自定义报错回复信息。配置后将优先发送给最终用户。"""

    # cache
    _begin_dialogs_processed: list[dict]
