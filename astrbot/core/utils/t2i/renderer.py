from .local_strategy import LocalRenderStrategy
from .runtime_stats import T2iRuntimeStats


class HtmlRenderer:
    def __init__(self) -> None:
        self.runtime_stats = T2iRuntimeStats()
        self.local_strategy = LocalRenderStrategy(self.runtime_stats)

    async def initialize(self) -> None:
        await self.local_strategy.initialize()

    async def terminate(self) -> None:
        await self.local_strategy.terminate()

    async def render_custom_template(
        self,
        tmpl_str: str,
        tmpl_data: dict,
        options: dict | None = None,
    ) -> str:
        """使用本地 Playwright 渲染 HTML/Jinja 模板并返回图片路径。"""
        return await self.local_strategy.render_custom_template(
            tmpl_str,
            tmpl_data,
            options,
        )

    async def render_t2i(
        self,
        text: str,
        template_name: str | None = None,
    ) -> str:
        """使用本地 Playwright 渲染文本并返回图片路径。"""
        return await self.local_strategy.render(
            text,
            template_name=template_name,
        )

    def get_runtime_stats(self) -> dict[str, int | float | bool]:
        """Return a non-sensitive local T2I runtime statistics snapshot."""
        return self.local_strategy.get_runtime_stats()
