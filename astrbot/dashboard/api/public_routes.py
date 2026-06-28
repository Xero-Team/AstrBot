import json
import mimetypes
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlencode, urlsplit

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from astrbot.core.star.star import StarMetadata
from astrbot.dashboard.responses import ok
from astrbot.dashboard.schemas import LoginRequest
from astrbot.dashboard.services.auth_service import AuthService
from astrbot.dashboard.services.plugin_service import PluginService
from astrbot.dashboard.services.stat_service import StatService

from .auth import (
    _clear_dashboard_jwt_cookie,
    _login,
    get_auth_service,
)
from .stats import get_service as get_stat_service

router = APIRouter(include_in_schema=False)

_RELATIVE_HTML_ASSET_RE = re.compile(
    r'(?P<attr>src|href)=(?P<quote>["\'])(?P<path>[^"\']+)(?P=quote)'
)
_RELATIVE_JS_IMPORT_RE = re.compile(
    r'(?P<quote>["\'])(?P<path>\.{1,2}/[^"\']+)(?P=quote)'
)
_RELATIVE_CSS_URL_RE = re.compile(
    r'url\((?P<quote>["\']?)(?P<path>[^)"\']+)(?P=quote)\)'
)


def _plugin_service(request: Request) -> PluginService:
    return request.app.state.services.plugins


def _find_plugin(service: PluginService, plugin_name: str) -> StarMetadata:
    for plugin in service.plugin_manager.context.get_all_stars():
        if plugin.name == plugin_name:
            return plugin
    raise HTTPException(status_code=404, detail="Plugin not found")


def _plugin_root(service: PluginService, plugin: StarMetadata) -> Path:
    plugin_dir_name = str(plugin.root_dir_name or plugin.name or "").strip()
    if not plugin_dir_name:
        raise HTTPException(status_code=404, detail="Plugin root missing")
    return Path(service.plugin_manager.plugin_store_path) / plugin_dir_name


def _page_root(plugin_root: Path, page_name: str) -> Path:
    page_root = plugin_root / "pages" / page_name
    if not page_root.is_dir() or not (page_root / "index.html").is_file():
        raise HTTPException(status_code=404, detail="Plugin page not found")
    return page_root


def _normalize_theme(theme: str | None) -> str | None:
    return theme if theme in {"dark", "light"} else None


def _load_plugin_i18n(plugin_root: Path) -> tuple[str, dict]:
    i18n_root = plugin_root / ".astrbot-plugin" / "i18n"
    if not i18n_root.is_dir():
        return "zh-CN", {}

    preferred_path = i18n_root / "zh-CN.json"
    if preferred_path.is_file():
        return "zh-CN", json.loads(preferred_path.read_text(encoding="utf-8"))

    for path in sorted(i18n_root.glob("*.json")):
        return path.stem, json.loads(path.read_text(encoding="utf-8"))
    return "zh-CN", {}


def _plugin_page_texts(
    plugin: StarMetadata, plugin_root: Path, page_name: str
) -> tuple[str, str, str]:
    locale, i18n_payload = _load_plugin_i18n(plugin_root)
    metadata_payload = i18n_payload.get("metadata", {})
    pages_payload = i18n_payload.get("pages", {})
    display_name = str(
        metadata_payload.get("display_name") or plugin.display_name or plugin.name or ""
    )
    page_payload = pages_payload.get(page_name, {})
    page_title = str(page_payload.get("title") or page_name)
    return locale, display_name, page_title


def _current_username(request: Request) -> str:
    dashboard_g = getattr(request.state, "dashboard_g", None)
    username = getattr(dashboard_g, "username", None)
    if isinstance(username, str) and username.strip():
        return username
    raise HTTPException(status_code=401, detail="Unauthorized")


def _build_asset_token(request: Request, plugin_name: str, page_name: str) -> str:
    payload = {
        "username": _current_username(request),
        "token_type": "plugin_page_asset",
        "plugin_name": plugin_name,
        "page_name": page_name,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(payload, request.app.state.jwt_secret, algorithm="HS256")


def _join_query(
    path: str,
    *,
    asset_token: str | None = None,
    theme: str | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    params: dict[str, str] = {}
    if asset_token:
        params["asset_token"] = asset_token
    if theme:
        params["theme"] = theme
    if extra:
        params.update(extra)
    if not params:
        return path
    return f"{path}?{urlencode(params)}"


def _content_url(
    plugin_name: str,
    page_name: str,
    asset_path: str,
    *,
    asset_token: str | None,
    theme: str | None,
) -> str:
    quoted_plugin = quote(plugin_name, safe="")
    quoted_page = quote(page_name, safe="")
    if asset_path:
        quoted_asset = quote(asset_path, safe="/")
        base_path = (
            f"/api/plugin/page/content/{quoted_plugin}/{quoted_page}/{quoted_asset}"
        )
    else:
        base_path = f"/api/plugin/page/content/{quoted_plugin}/{quoted_page}/"
    return _join_query(base_path, asset_token=asset_token, theme=theme)


def _bridge_url(
    plugin_name: str, page_name: str, *, asset_token: str | None, theme: str | None
) -> str:
    return _join_query(
        "/api/plugin/page/bridge-sdk.js",
        asset_token=asset_token,
        theme=theme,
        extra={"plugin_name": plugin_name, "page_name": page_name},
    )


def _resolve_relative_asset(current_path: str, target: str) -> str | None:
    if target.startswith(("/", "#", "data:", "javascript:")):
        return None
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None

    raw_path = parsed.path or ""
    base_dir = PurePosixPath(current_path).parent if current_path else PurePosixPath()
    normalized = PurePosixPath(base_dir, raw_path).as_posix()
    normalized = str(PurePosixPath(normalized))
    if normalized.startswith("../") or normalized == "..":
        raise HTTPException(status_code=404, detail="Invalid asset path")
    return normalized


def _rewrite_html_content(
    html_text: str,
    plugin_name: str,
    page_name: str,
    *,
    asset_token: str,
    theme: str | None,
) -> str:
    def replace_asset(match: re.Match[str]) -> str:
        asset_path = _resolve_relative_asset("", match.group("path"))
        if asset_path is None:
            return match.group(0)
        rewritten = _content_url(
            plugin_name,
            page_name,
            asset_path,
            asset_token=asset_token,
            theme=theme,
        )
        return f"{match.group('attr')}={match.group('quote')}{rewritten}{match.group('quote')}"

    rewritten = _RELATIVE_HTML_ASSET_RE.sub(replace_asset, html_text)
    bridge_script = f'<script src="{_bridge_url(plugin_name, page_name, asset_token=asset_token, theme=theme)}"></script>'
    if "</body>" in rewritten:
        rewritten = rewritten.replace("</body>", f"{bridge_script}\n  </body>", 1)
    else:
        rewritten += bridge_script

    if theme:
        rewritten = rewritten.replace("<html", f'<html data-theme="{theme}"', 1)
        color_scheme_meta = f'<meta name="color-scheme" content="{theme}">'
        if "<head>" in rewritten:
            rewritten = rewritten.replace(
                "<head>", f"<head>\n    {color_scheme_meta}", 1
            )
        else:
            rewritten = color_scheme_meta + rewritten
    return rewritten


def _rewrite_js_content(
    js_text: str,
    plugin_name: str,
    page_name: str,
    current_asset_path: str,
    *,
    asset_token: str,
    theme: str | None,
) -> str:
    def replace_import(match: re.Match[str]) -> str:
        asset_path = _resolve_relative_asset(current_asset_path, match.group("path"))
        if asset_path is None:
            return match.group(0)
        rewritten = _content_url(
            plugin_name,
            page_name,
            asset_path,
            asset_token=asset_token,
            theme=theme,
        )
        return f"{match.group('quote')}{rewritten}{match.group('quote')}"

    return _RELATIVE_JS_IMPORT_RE.sub(replace_import, js_text)


def _rewrite_css_content(
    css_text: str,
    plugin_name: str,
    page_name: str,
    current_asset_path: str,
    *,
    asset_token: str,
    theme: str | None,
) -> str:
    def replace_url(match: re.Match[str]) -> str:
        asset_path = _resolve_relative_asset(current_asset_path, match.group("path"))
        if asset_path is None:
            return match.group(0)
        rewritten = _content_url(
            plugin_name,
            page_name,
            asset_path,
            asset_token=asset_token,
            theme=theme,
        )
        quote_char = match.group("quote")
        return f"url({quote_char}{rewritten}{quote_char})"

    return _RELATIVE_CSS_URL_RE.sub(replace_url, css_text)


def _plugin_page_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "X-Frame-Options": "SAMEORIGIN",
        "Content-Security-Policy": "frame-ancestors 'self'",
    }


@router.post("/api/auth/login")
async def login_alias(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    return await _login(request, payload, service)


@router.post("/api/auth/logout")
async def logout_alias(request: Request):
    response = JSONResponse(
        {"status": "ok", "message": "已退出登录", "data": {}},
        status_code=200,
    )
    _clear_dashboard_jwt_cookie(request, response)
    return response


@router.get("/api/stat/versions")
async def public_versions_alias(
    request: Request,
    service: StatService = Depends(get_stat_service),
):
    return ok(
        await service.get_public_versions(
            getattr(request.app.state, "dashboard_static_folder", None)
        )
    )


@router.get("/api/plugin/page/entry")
async def plugin_page_entry(
    request: Request,
    name: str = Query(...),
    page: str = Query(...),
    service: PluginService = Depends(_plugin_service),
):
    plugin = _find_plugin(service, name)
    plugin_root = _plugin_root(service, plugin)
    _page_root(plugin_root, page)
    asset_token = _build_asset_token(request, name, page)
    return ok(
        {
            "name": page,
            "title": page,
            "page_name": page,
            "i18n_key": f"pages.{page}",
            "content_path": _content_url(
                name,
                page,
                "",
                asset_token=asset_token,
                theme=None,
            ),
        }
    )


@router.get("/api/plugin/page/bridge-sdk.js")
async def plugin_page_bridge_sdk(
    request: Request,
    plugin_name: str = Query(...),
    page_name: str = Query(...),
    service: PluginService = Depends(_plugin_service),
):
    plugin = _find_plugin(service, plugin_name)
    plugin_root = _plugin_root(service, plugin)
    _page_root(plugin_root, page_name)
    locale, display_name, page_title = _plugin_page_texts(
        plugin, plugin_root, page_name
    )
    is_dark = _normalize_theme(request.query_params.get("theme")) == "dark"
    bridge_js = (
        "window.AstrBotPluginPage = window.AstrBotPluginPage || {};\n"
        "window.AstrBotPluginPage.__setInitialContext = window.AstrBotPluginPage.__setInitialContext || "
        "function(ctx) { window.AstrBotPluginPage.__initialContext = ctx; };\n"
        f"window.AstrBotPluginPage?.__setInitialContext({json.dumps({'locale': locale, 'displayName': display_name, 'pageTitle': page_title, 'isDark': is_dark}, ensure_ascii=False)});\n"
    )
    return Response(
        content=bridge_js,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/plugin/page/content/{plugin_name}/{page_name}/")
@router.get("/api/plugin/page/content/{plugin_name}/{page_name}/{asset_path:path}")
async def plugin_page_content(
    request: Request,
    plugin_name: str,
    page_name: str,
    asset_path: str = "",
    service: PluginService = Depends(_plugin_service),
):
    plugin = _find_plugin(service, plugin_name)
    plugin_root = _plugin_root(service, plugin)
    page_root = _page_root(plugin_root, page_name)
    normalized_theme = _normalize_theme(request.query_params.get("theme"))
    asset_token = request.query_params.get(
        "asset_token", ""
    ).strip() or _build_asset_token(
        request,
        plugin_name,
        page_name,
    )

    relative_asset = asset_path.strip("/")
    asset_file = (
        page_root / "index.html" if not relative_asset else page_root / relative_asset
    )
    resolved_page_root = page_root.resolve()
    resolved_asset_file = asset_file.resolve(strict=False)
    if not resolved_asset_file.is_relative_to(resolved_page_root):
        raise HTTPException(status_code=404, detail="Invalid asset path")
    if resolved_asset_file.is_dir():
        resolved_asset_file = resolved_asset_file / "index.html"
    if not resolved_asset_file.is_file():
        raise HTTPException(status_code=404, detail="Plugin asset not found")

    suffix = resolved_asset_file.suffix.lower()
    if suffix in {".html", ".js", ".css"}:
        file_text = resolved_asset_file.read_text(encoding="utf-8")
        if suffix == ".html":
            file_text = _rewrite_html_content(
                file_text,
                plugin_name,
                page_name,
                asset_token=asset_token,
                theme=normalized_theme,
            )
            media_type = "text/html; charset=utf-8"
        elif suffix == ".js":
            file_text = _rewrite_js_content(
                file_text,
                plugin_name,
                page_name,
                relative_asset,
                asset_token=asset_token,
                theme=normalized_theme,
            )
            media_type = "application/javascript"
        else:
            file_text = _rewrite_css_content(
                file_text,
                plugin_name,
                page_name,
                relative_asset,
                asset_token=asset_token,
                theme=normalized_theme,
            )
            media_type = "text/css; charset=utf-8"
        return Response(
            content=file_text,
            media_type=media_type,
            headers=_plugin_page_headers(),
        )

    guessed_media_type = mimetypes.guess_type(resolved_asset_file.name)[0]
    return FileResponse(
        resolved_asset_file,
        media_type=guessed_media_type,
        headers={"Cache-Control": "no-store"},
    )
