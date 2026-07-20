import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.utils.t2i import local_strategy
from astrbot.core.utils.t2i.local_strategy import LocalRenderStrategy, ScreenshotOptions
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from astrbot.core.utils.t2i.template_runtime import render_markdown


@pytest.mark.asyncio
async def test_render_t2i_uses_only_local_strategy():
    renderer = HtmlRenderer()
    renderer.local_strategy.render = AsyncMock(return_value="D:/temp/local.png")

    result = await renderer.render_t2i("hello", template_name="astrbot_help")

    renderer.local_strategy.render.assert_awaited_once_with(
        "hello",
        template_name="astrbot_help",
    )
    assert result == "D:/temp/local.png"
    assert not hasattr(renderer, "network_strategy")


@pytest.mark.asyncio
async def test_render_custom_template_uses_only_local_strategy():
    renderer = HtmlRenderer()
    renderer.local_strategy.render_custom_template = AsyncMock(
        return_value="D:/temp/local.png"
    )

    result = await renderer.render_custom_template(
        "<html>{{ text }}</html>",
        {"text": "hello"},
        options={"type": "png"},
    )

    renderer.local_strategy.render_custom_template.assert_awaited_once_with(
        "<html>{{ text }}</html>",
        {"text": "hello"},
        {"type": "png"},
    )
    assert result == "D:/temp/local.png"


@pytest.mark.asyncio
async def test_renderer_terminate_delegates_to_local_strategy():
    renderer = HtmlRenderer()
    renderer.local_strategy.terminate = AsyncMock()

    await renderer.terminate()

    renderer.local_strategy.terminate.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_strategy_terminate_cleans_playwright_resources():
    strategy = LocalRenderStrategy()
    context_a = MagicMock()
    context_a.close = AsyncMock()
    context_b = MagicMock()
    context_b.close = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    playwright = MagicMock()
    playwright.stop = AsyncMock()

    strategy.contexts = {"normal": context_a, "ultra": context_b}
    strategy.browser = browser
    strategy.playwright = playwright

    await strategy.terminate()

    context_a.close.assert_awaited_once()
    context_b.close.assert_awaited_once()
    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()
    assert strategy.contexts == {}
    assert strategy.browser is None
    assert strategy.playwright is None


@pytest.mark.asyncio
async def test_local_strategy_serializes_browser_initialization(monkeypatch):
    strategy = LocalRenderStrategy()
    context = MagicMock()
    browser = MagicMock()
    browser.is_connected.return_value = True
    browser.new_context = AsyncMock(return_value=context)
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=browser)

    class PlaywrightFactory:
        async def start(self):
            await asyncio.sleep(0)
            return playwright

    monkeypatch.setattr(local_strategy, "async_playwright", PlaywrightFactory)

    contexts = await asyncio.gather(
        strategy._ensure_context(),
        strategy._ensure_context(),
        strategy._ensure_context(),
    )

    assert contexts == [context, context, context]
    playwright.chromium.launch.assert_awaited_once_with(headless=True)
    browser.new_context.assert_awaited_once_with(device_scale_factor=1.0)


@pytest.mark.asyncio
async def test_local_strategy_discards_contexts_when_browser_restarts(monkeypatch):
    strategy = LocalRenderStrategy()
    stale_context = MagicMock()
    stale_context.close = AsyncMock()
    stale_browser = MagicMock()
    stale_browser.is_connected.return_value = False
    stale_browser.close = AsyncMock()
    fresh_context = MagicMock()
    fresh_browser = MagicMock()
    fresh_browser.new_context = AsyncMock(return_value=fresh_context)
    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(return_value=fresh_browser)
    strategy.browser = stale_browser
    strategy.contexts = {"normal": stale_context}

    class PlaywrightFactory:
        async def start(self):
            return playwright

    monkeypatch.setattr(local_strategy, "async_playwright", PlaywrightFactory)

    context = await strategy._ensure_context()

    assert context is fresh_context
    stale_context.close.assert_awaited_once()
    stale_browser.close.assert_awaited_once()
    fresh_browser.new_context.assert_awaited_once_with(device_scale_factor=1.0)
    assert strategy.get_runtime_stats()["browser_restarts"] == 1


@pytest.mark.asyncio
async def test_local_strategy_removes_intermediate_html_file(tmp_path):
    strategy = LocalRenderStrategy()
    strategy.temp_dir = tmp_path
    page = MagicMock()
    page.route = AsyncMock()
    page.goto = AsyncMock()
    page.set_viewport_size = AsyncMock()
    page.close = AsyncMock()

    async def screenshot(**kwargs):
        Path(kwargs["path"]).write_bytes(b"png")

    page.screenshot = AsyncMock(side_effect=screenshot)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    strategy._ensure_context = AsyncMock(return_value=context)

    image_path = await strategy._render_html_to_image(
        "<html><body>test</body></html>",
        ScreenshotOptions(type="png"),
    )

    assert Path(image_path).exists()
    assert not list(tmp_path.glob("*.html"))
    page.close.assert_awaited_once()
    page.set_viewport_size.assert_awaited_once_with({"width": 1280, "height": 720})


@pytest.mark.asyncio
async def test_local_strategy_removes_partial_files_on_render_failure(tmp_path):
    strategy = LocalRenderStrategy()
    strategy.temp_dir = tmp_path
    page = MagicMock()
    page.route = AsyncMock()
    page.goto = AsyncMock()
    page.set_viewport_size = AsyncMock()
    page.screenshot = AsyncMock(side_effect=RuntimeError("screenshot failed"))
    page.close = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    strategy._ensure_context = AsyncMock(return_value=context)

    with pytest.raises(RuntimeError, match="screenshot failed"):
        await strategy._render_html_to_image(
            "<html><body>test</body></html>",
            ScreenshotOptions(type="png"),
        )

    assert not list(tmp_path.iterdir())
    assert strategy.get_runtime_stats()["failed_renders"] == 1


@pytest.mark.asyncio
async def test_local_strategy_records_cancelled_renders(tmp_path):
    strategy = LocalRenderStrategy()
    strategy.temp_dir = tmp_path
    page = MagicMock()
    page.route = AsyncMock()
    page.set_viewport_size = AsyncMock()
    page.goto = AsyncMock(side_effect=asyncio.CancelledError())
    page.close = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    strategy._ensure_context = AsyncMock(return_value=context)

    with pytest.raises(asyncio.CancelledError):
        await strategy._render_html_to_image(
            "<html><body>test</body></html>",
            ScreenshotOptions(type="png"),
        )

    stats = strategy.get_runtime_stats()
    assert stats["cancelled_renders"] == 1
    assert stats["render_in_progress"] == 0
    assert stats["active_pages"] == 0


@pytest.mark.asyncio
async def test_local_strategy_uses_html_meta_viewport_and_blocks_remote_requests(
    tmp_path,
):
    strategy = LocalRenderStrategy()
    strategy.temp_dir = tmp_path
    page = MagicMock()
    page.route = AsyncMock()
    page.goto = AsyncMock()
    page.set_viewport_size = AsyncMock()
    page.close = AsyncMock()

    async def screenshot(**kwargs):
        Path(kwargs["path"]).write_bytes(b"png")

    page.screenshot = AsyncMock(side_effect=screenshot)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    strategy._ensure_context = AsyncMock(return_value=context)

    image_path = await strategy._render_html_to_image(
        '<meta name="viewport" content="width=640; height=360">',
        ScreenshotOptions(type="png", viewport_width=None),
    )

    route_handler = page.route.await_args.args[1]
    remote_route = MagicMock()
    remote_route.request.url = "https://example.com/style.css"
    remote_route.abort = AsyncMock()
    remote_route.continue_ = AsyncMock()
    await route_handler(remote_route)

    local_route = MagicMock()
    local_route.request.url = "file:///tmp/local.css"
    local_route.abort = AsyncMock()
    local_route.continue_ = AsyncMock()
    await route_handler(local_route)

    assert Path(image_path).exists()
    page.set_viewport_size.assert_awaited_once_with({"width": 640, "height": 360})
    remote_route.abort.assert_awaited_once()
    remote_route.continue_.assert_not_awaited()
    local_route.abort.assert_not_awaited()
    local_route.continue_.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_strategy_recreates_closed_context_once(monkeypatch, tmp_path):
    class ClosedContextError(Exception):
        pass

    monkeypatch.setattr(local_strategy, "TargetClosedError", ClosedContextError)
    strategy = LocalRenderStrategy()
    strategy.temp_dir = tmp_path
    closed_context = MagicMock()
    closed_context.close = AsyncMock()
    replacement_context = MagicMock()
    page = MagicMock()
    page.route = AsyncMock()
    page.goto = AsyncMock()
    page.set_viewport_size = AsyncMock()
    page.close = AsyncMock()

    async def screenshot(**kwargs):
        Path(kwargs["path"]).write_bytes(b"png")

    page.screenshot = AsyncMock(side_effect=screenshot)
    closed_context.new_page = AsyncMock(side_effect=ClosedContextError("closed"))
    replacement_context.new_page = AsyncMock(return_value=page)
    strategy.contexts = {"normal": closed_context}
    strategy._ensure_context = AsyncMock(
        side_effect=[closed_context, replacement_context],
    )

    image_path = await strategy._render_html_to_image(
        "<html><body>test</body></html>",
        ScreenshotOptions(type="png"),
    )

    assert Path(image_path).exists()
    closed_context.close.assert_awaited_once()
    replacement_context.new_page.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_strategy_records_non_sensitive_runtime_statistics(tmp_path):
    strategy = LocalRenderStrategy()
    strategy.temp_dir = tmp_path
    page = MagicMock()
    page.route = AsyncMock()
    page.goto = AsyncMock()
    page.set_viewport_size = AsyncMock()
    page.close = AsyncMock()

    async def screenshot(**kwargs):
        Path(kwargs["path"]).write_bytes(b"png")

    page.screenshot = AsyncMock(side_effect=screenshot)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    strategy._ensure_context = AsyncMock(return_value=context)

    image_path = await strategy._render_html_to_image(
        "<html><body>test</body></html>",
        ScreenshotOptions(type="png"),
    )

    stats = strategy.get_runtime_stats()

    assert Path(image_path).exists()
    assert stats["successful_renders"] == 1
    assert stats["failed_renders"] == 0
    assert stats["render_in_progress"] == 0
    assert stats["active_pages"] == 0
    assert stats["output_bytes"] == 3
    assert "template" not in stats
    assert "path" not in stats


def test_render_markdown_escapes_raw_html():
    rendered = render_markdown('<script>alert("x")</script>')

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_render_markdown_renders_math_locally():
    rendered = render_markdown("Inline $a+b$ and block:\n\n$$\\frac{1}{2}$$")

    assert "<math" in rendered
    assert "\\frac{1}{2}" in rendered
