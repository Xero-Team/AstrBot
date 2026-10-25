from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.skills.skill_manager import SkillManager
from astrbot.dashboard.services.skills_service import SkillsService, SkillsServiceError


def _build_manager(tmp_path: Path) -> tuple[SkillManager, Path, Path]:
    root = tmp_path / "root"
    skills_root = root / "data" / "skills"
    skills_root.mkdir(parents=True)
    demo_dir = skills_root / "demo"
    demo_dir.mkdir()
    (demo_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n",
        encoding="utf-8",
    )
    sentinel = root / "data" / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    manager = SkillManager(
        skills_root=str(skills_root),
        plugins_root=str(tmp_path / "plugins"),
    )
    manager.config_path = str(tmp_path / "skills.json")
    manager.sandbox_skills_cache_path = str(tmp_path / "sandbox-cache.json")
    return manager, skills_root, sentinel


def _build_service(manager: SkillManager) -> SkillsService:
    return SkillsService(
        {},
        SimpleNamespace(sync_skills_to_active_sandboxes=lambda: None),
        manager,
        demo_mode=False,
    )


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../escape", "nested/name", "/absolute", "nested\\name"],
)
def test_delete_skill_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    manager, skills_root, sentinel = _build_manager(tmp_path)

    with pytest.raises(ValueError):
        manager.delete_skill(name)

    assert skills_root.is_dir()
    assert sentinel.exists()


@pytest.mark.parametrize("name", ["", ".", "..", "../escape", "nested/name"])
def test_set_skill_active_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    manager, _skills_root, _sentinel = _build_manager(tmp_path)

    with pytest.raises(ValueError):
        manager.set_skill_active(name, True)

    assert not Path(manager.config_path).exists()


def test_delete_skill_still_deletes_a_valid_skill(tmp_path: Path) -> None:
    manager, skills_root, sentinel = _build_manager(tmp_path)

    manager.delete_skill("demo")

    assert not (skills_root / "demo").exists()
    assert sentinel.exists()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs extra privileges")
def test_delete_skill_unlinks_symlink_without_touching_target(tmp_path: Path) -> None:
    manager, skills_root, sentinel = _build_manager(tmp_path)
    alias = skills_root / "alias"
    alias.symlink_to(skills_root / "demo", target_is_directory=True)

    manager.delete_skill("alias")

    assert not alias.exists()
    assert (skills_root / "demo" / "SKILL.md").exists()
    assert sentinel.exists()


@pytest.mark.asyncio
async def test_service_delete_rejects_parent_directory_name(tmp_path: Path) -> None:
    manager, skills_root, sentinel = _build_manager(tmp_path)
    service = _build_service(manager)

    with pytest.raises(SkillsServiceError):
        await service.delete_skill({"name": ".."})

    assert skills_root.is_dir()
    assert sentinel.exists()


@pytest.mark.asyncio
async def test_service_update_rejects_path_separator(tmp_path: Path) -> None:
    manager, _skills_root, _sentinel = _build_manager(tmp_path)
    service = _build_service(manager)

    with pytest.raises(SkillsServiceError):
        service.update_skill({"name": "../escape", "active": False})

    assert not Path(manager.config_path).exists()


def test_prepare_skill_archive_rejects_parent_name(tmp_path: Path) -> None:
    manager, _skills_root, _sentinel = _build_manager(tmp_path)
    service = _build_service(manager)

    with pytest.raises(SkillsServiceError):
        service.prepare_skill_archive("..")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs extra privileges")
def test_prepare_skill_archive_rejects_symlinked_skill_dir(tmp_path: Path) -> None:
    manager, skills_root, _sentinel = _build_manager(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: outside\ndescription: outside\n---\n",
        encoding="utf-8",
    )
    (skills_root / "outside").symlink_to(outside, target_is_directory=True)
    service = _build_service(manager)

    with pytest.raises(SkillsServiceError):
        service.prepare_skill_archive("outside")
