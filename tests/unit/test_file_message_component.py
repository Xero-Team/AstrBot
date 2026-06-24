from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.message import components


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

    monkeypatch.setattr(
        components,
        "astrbot_config",
        SimpleNamespace(
            get=lambda key, default=None: (
                "https://example.com" if key == "callback_api_base" else default
            )
        ),
    )
    monkeypatch.setattr(
        components.file_token_service, "register_file", fake_register_file
    )

    component = components.File(name="report.txt", file=str(file_path))

    url = await component.register_to_file_service()

    assert url == "https://example.com/api/v1/files/tokens/token-123"


@pytest.mark.asyncio
async def test_file_component_to_dict_uses_v1_file_token_url(monkeypatch, tmp_path):
    file_path = tmp_path / "report.txt"
    file_path.write_text("payload", encoding="utf-8")

    async def fake_register_file(path: str) -> str:
        assert path == str(file_path)
        return "token-456"

    monkeypatch.setattr(
        components,
        "astrbot_config",
        SimpleNamespace(
            get=lambda key, default=None: (
                "https://example.com/" if key == "callback_api_base" else default
            )
        ),
    )
    monkeypatch.setattr(
        components.file_token_service, "register_file", fake_register_file
    )

    component = components.File(name="report.txt", file=str(file_path))

    payload = await component.to_dict()

    assert (
        payload["data"]["file"] == "https://example.com/api/v1/files/tokens/token-456"
    )
