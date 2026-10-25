from pathlib import Path

import pytest

from astrbot.core.utils.t2i import template_manager
from astrbot.core.utils.t2i.template_manager import TemplateManager


@pytest.fixture
def template_paths(tmp_path: Path, monkeypatch):
    root = tmp_path / "root"
    builtin_dir = root / "astrbot" / "core" / "utils" / "t2i" / "template"
    builtin_dir.mkdir(parents=True)
    data_dir = tmp_path / "data"
    for filename in TemplateManager.CORE_TEMPLATES:
        (builtin_dir / filename).write_text(f"builtin {filename}", encoding="utf-8")

    monkeypatch.setattr(template_manager, "get_astrbot_path", lambda: str(root))
    monkeypatch.setattr(
        template_manager, "get_astrbot_data_path", lambda: str(data_dir)
    )
    return builtin_dir, data_dir / "t2i_templates"


def test_template_manager_does_not_copy_builtin_templates(template_paths):
    builtin_dir, user_dir = template_paths

    manager = TemplateManager()

    assert not (user_dir / "base.html").exists()
    assert manager.get_template("base") == (builtin_dir / "base.html").read_text(
        encoding="utf-8"
    )


def test_template_manager_keeps_explicit_core_override(template_paths):
    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "base.html").write_text("custom template", encoding="utf-8")

    manager = TemplateManager()

    assert manager.get_template("base") == "custom template"


def test_reset_default_template_removes_core_overrides_only(template_paths):
    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "base.html").write_text("custom base", encoding="utf-8")
    (user_dir / "custom.html").write_text("custom", encoding="utf-8")
    manager = TemplateManager()

    manager.reset_default_template()

    assert manager.get_template("base") == "builtin base.html"
    assert manager.get_template("custom") == "custom"


def test_builtin_base_template_stays_offline():
    content = (
        (
            Path(__file__).resolve().parents[2]
            / "astrbot"
            / "core"
            / "utils"
            / "t2i"
            / "template"
            / "base.html"
        )
        .read_text(encoding="utf-8")
        .replace("\r\n", "\n")
    )

    assert "https://fonts.googleapis.com" not in content
    assert "cdn.jsdelivr.net" not in content
    assert 'src="http' not in content
    assert 'href="http' not in content
    assert "{{ rendered_html | safe }}" in content
    assert "markdown-source" not in content
    assert "marked.min.js" not in content


def test_internal_help_template_is_not_selectable_for_generic_rendering():
    from astrbot.core.utils.t2i.template_manager import public_template_name

    assert public_template_name("astrbot_help") == "base"
    assert public_template_name("AstrBot_Help") == "base"
    assert public_template_name(" ASTRBOT_HELP ") == "base"
    assert public_template_name("custom") == "custom"
    assert public_template_name(None) == "base"


@pytest.mark.asyncio
async def test_t2i_service_rejects_internal_template_as_active():
    from astrbot.dashboard.services.t2i_service import T2iService, T2iServiceError

    service = T2iService.__new__(T2iService)

    for name in ("astrbot_help", "AstrBot_Help", " ASTRBOT_HELP "):
        with pytest.raises(T2iServiceError):
            await service.set_active_template(name)


def test_builtin_help_template_ignores_user_override(template_paths):
    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "astrbot_help.html").write_text("override", encoding="utf-8")

    manager = TemplateManager()

    assert manager.get_template("astrbot_help") == "override"
    assert manager.get_builtin_template("astrbot_help") == "builtin astrbot_help.html"


@pytest.mark.asyncio
async def test_render_help_uses_the_builtin_template(template_paths):
    from astrbot.core.utils.t2i.local_strategy import HtmlRenderer

    _, user_dir = template_paths
    user_dir.mkdir(parents=True)
    (user_dir / "astrbot_help.html").write_text("override", encoding="utf-8")

    renderer = HtmlRenderer.__new__(HtmlRenderer)
    renderer.template_manager = TemplateManager()
    captured: dict[str, str] = {}

    async def fake_render(tmpl_str: str, _data: dict) -> str:
        captured["template"] = tmpl_str
        return "image"

    renderer.render_custom_template = fake_render

    assert await renderer.render_help("help") == "image"
    assert captured["template"] == "builtin astrbot_help.html"


@pytest.mark.asyncio
async def test_t2i_service_rejects_changes_to_internal_templates():
    from astrbot.dashboard.services.t2i_service import T2iService, T2iServiceError

    service = T2iService.__new__(T2iService)

    with pytest.raises(T2iServiceError):
        service.create_template("astrbot_help", "override")
    with pytest.raises(T2iServiceError):
        await service.update_template("astrbot_help", "override")
