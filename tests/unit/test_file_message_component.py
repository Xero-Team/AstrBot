from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.message import components


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component_factory", "source", "expected"),
    [
        (lambda: components.Record(file=None), "https://example.com/a.mp3", "url"),
        (lambda: components.Video(file=""), "file:///tmp/a.mp4", "url"),
        (lambda: components.Image(file=None), "data:image/png;base64,AA==", "url"),
        (lambda: components.Record(file=None), "base64://AA==", "url"),
        (lambda: components.Video(file=""), "/tmp/a.mp4", "path"),
        (lambda: components.Image(file=None), None, None),
    ],
)
async def test_deferred_media_sources_resolve_once_and_preserve_source_mapping(
    component_factory, source, expected
):
    calls = 0

    async def resolve():
        nonlocal calls
        calls += 1
        return source

    component = component_factory()
    component.set_source_resolver(resolve)
    await component._resolve_deferred_source()
    await component._resolve_deferred_source()

    assert calls == 1
    if expected == "url":
        assert component.file == source
        assert component.url == source
    elif expected == "path":
        assert component.file == source
        assert component.path == source
    else:
        assert not component.file
        assert not component.url
        assert not component.path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "component",
    [
        components.Record(file="https://example.com/a.mp3"),
        components.Video(file="https://example.com/a.mp4"),
        components.Image(file="https://example.com/a.png"),
    ],
)
async def test_deferred_media_sources_do_not_replace_existing_source(component):
    async def resolve():
        raise AssertionError("resolver must not run")

    component.set_source_resolver(resolve)
    await component._resolve_deferred_source()


@pytest.mark.asyncio
async def test_file_component_download_sanitizes_remote_name(monkeypatch, tmp_path):
    temp_dir = tmp_path / "temp"
    downloaded_paths: list[Path] = []

    async def fake_download_file(url: str, path: str) -> None:
        target = Path(path)
        assert url == "https://example.com/report"
        assert target.parent == temp_dir
        assert target.parent.exists()
        assert "\x00" not in target.name
        assert "/" not in target.name
        assert "\\" not in target.name
        assert not any(char in target.name for char in ':*?"<>|')
        target.write_bytes(b"payload")
        downloaded_paths.append(target)

    monkeypatch.setattr(components, "download_file", fake_download_file)
    monkeypatch.setattr(components, "get_astrbot_temp_path", lambda: str(temp_dir))

    component = components.File(
        name='..\\nested/evil\\report:*?"<>|\x00.pdf',
        url="https://example.com/report",
    )

    path = Path(await component.get_file())

    assert path.parent == temp_dir
    assert path.exists()
    assert path.name.startswith("fileseg_report________")
    assert path.suffix == ".pdf"
    assert downloaded_paths == [path]


@pytest.mark.asyncio
async def test_file_component_registers_v1_file_token_url(monkeypatch, tmp_path):
    file_path = tmp_path / "report.txt"
    file_path.write_text("payload", encoding="utf-8")

    async def fake_register_file(path: str) -> str:
        assert path == str(file_path)
        return "token-123"

    component = components.File(name="report.txt", file=str(file_path))
    component.bind_file_service(
        "https://example.com",
        SimpleNamespace(register_file=fake_register_file),
    )

    url = await component.register_to_file_service()

    assert url == "https://example.com/api/v1/files/tokens/token-123"


@pytest.mark.asyncio
async def test_file_component_to_dict_uses_v1_file_token_url(monkeypatch, tmp_path):
    file_path = tmp_path / "report.txt"
    file_path.write_text("payload", encoding="utf-8")

    async def fake_register_file(path: str) -> str:
        assert path == str(file_path)
        return "token-456"

    component = components.File(name="report.txt", file=str(file_path))
    component.bind_file_service(
        "https://example.com/",
        SimpleNamespace(register_file=fake_register_file),
    )

    payload = await component.to_dict()

    assert (
        payload["data"]["file"] == "https://example.com/api/v1/files/tokens/token-456"
    )
