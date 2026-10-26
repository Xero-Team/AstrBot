from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from astrbot.core.star.plugin_package_installer import PluginPackageInstaller
from astrbot.core.star.updator import PluginUpdator


@pytest.mark.asyncio
async def test_extraction_failure_keeps_the_installed_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = tmp_path / "plugins"
    plugin_dir = store / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "main.py").write_text("VALUE = 'old'\n", encoding="utf-8")

    updater = PluginUpdator.__new__(PluginUpdator)
    updater.plugin_store_path = str(store)
    plugin = SimpleNamespace(
        name="demo",
        repo="https://github.com/example/demo",
        root_dir_name="demo",
    )

    async def fake_download(plugin_path: str, *_args, **_kwargs) -> None:
        Path(plugin_path + ".zip").write_bytes(b"not-a-real-zip")

    monkeypatch.setattr(updater, "download_from_repo_url", fake_download)
    monkeypatch.setattr(updater, "validate_plugin_archive", lambda _path: None)
    monkeypatch.setattr(
        updater,
        "unzip_file",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("disk full")),
    )

    with pytest.raises(RuntimeError, match="disk full"):
        await updater.update(plugin)

    assert (plugin_dir / "main.py").read_text(encoding="utf-8") == "VALUE = 'old'\n"
    assert not list(store.glob(".plugin-update-*"))


@pytest.mark.asyncio
async def test_reload_failure_restores_the_previous_plugin_tree(tmp_path: Path):
    store = tmp_path / "plugins"
    target = store / "demo"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")

    staging_root = tmp_path / "staging"
    staged = staging_root / "plugin"
    staged.mkdir(parents=True)
    (staged / "new.txt").write_text("new", encoding="utf-8")
    (staged / "metadata.yaml").write_text(
        yaml.safe_dump(
            {"name": "demo", "desc": "demo", "version": "2.0.0", "author": "test"}
        ),
        encoding="utf-8",
    )

    plugin = SimpleNamespace(name="demo", root_dir_name="demo", reserved=False)
    loader = SimpleNamespace(
        plugin_dir_name_from_metadata=lambda _path: "demo",
        load_metadata=lambda **_kwargs: None,
        record_failed_install=lambda **_kwargs: None,
    )
    reload_calls = 0

    async def reload_plugin(_name):
        nonlocal reload_calls
        reload_calls += 1
        if reload_calls == 1:
            return False, "import failed"
        return True, None

    installer = PluginPackageInstaller.__new__(PluginPackageInstaller)
    installer._plugin_store_path = str(store)
    installer._staging_root = lambda: staging_root
    installer._plugin_config_path = str(tmp_path / "config")
    installer._background_tasks = set()
    installer._catalogs = SimpleNamespace(
        plugins=SimpleNamespace(
            get_by_name=lambda name: plugin if name == "demo" else None,
            all=lambda: [plugin],
        )
    )
    installer.ensure_requirements = AsyncMock()

    with pytest.raises(Exception, match="import failed"):
        await installer._install_from_staged_directory(
            str(staged),
            ignore_version_check=True,
            loader=loader,
            load_plugin=AsyncMock(return_value=(False, "unused")),
            reload_plugin=reload_plugin,
            terminate_plugin=None,
        )

    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (target / "new.txt").exists()
    assert reload_calls == 2
