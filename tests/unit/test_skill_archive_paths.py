import zipfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from astrbot.core.skills._skill_inventory import (
    _normalize_archive_entry_names,
    _validate_archive_paths,
)
from astrbot.core.skills.skill_manager import SkillManager

PROPERTY_SETTINGS = settings(
    database=None,
    deadline=None,
    derandomize=True,
    max_examples=100,
)

_UNICODE_COMPONENT = st.one_of(
    st.sampled_from(("工程", "naïve", "emoji🙂", "𝒜")),
    st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Lo", "Nd")),
        min_size=1,
        max_size=24,
    ),
)


@PROPERTY_SETTINGS
@given(_UNICODE_COMPONENT)
def test_skill_archive_path_validation_normalizes_safe_backslashes(
    component: str,
) -> None:
    names = _normalize_archive_entry_names([f"{component}\\nested\\SKILL.md"])

    assert names == [f"{component}/nested/SKILL.md"]
    _validate_archive_paths(names)


@PROPERTY_SETTINGS
@given(_UNICODE_COMPONENT)
def test_skill_archive_path_validation_rejects_cross_platform_escape_forms(
    component: str,
) -> None:
    unsafe_names = (
        f"../{component}/SKILL.md",
        f"nested\\..\\{component}\\SKILL.md",
        f"/{component}/SKILL.md",
        f"\\{component}\\SKILL.md",
        f"C:\\{component}\\SKILL.md",
        f"C:relative\\{component}\\SKILL.md",
        f"\\\\server\\share\\{component}\\SKILL.md",
        f"//server/share/{component}/SKILL.md",
        f"\\\\?\\C:\\{component}\\SKILL.md",
        f"{component}/\x1f/SKILL.md",
        f"{component}/\u0085/SKILL.md",
    )

    for unsafe_name in unsafe_names:
        names = _normalize_archive_entry_names([unsafe_name])
        with pytest.raises(ValueError):
            _validate_archive_paths(names)


def test_install_skill_from_zip_uses_normalized_unicode_backslash_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
    archive_path = tmp_path / "portable-skill.zip"
    data_root.mkdir()
    temp_root.mkdir()

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_root),
    )
    monkeypatch.setattr(
        "astrbot.core.skills._skill_manager_archive.get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("工程\\SKILL.md", "# Unicode skill\n")

    manager = SkillManager(skills_root=str(skills_root))

    assert manager.install_skill_from_zip(str(archive_path)) == "工程"
    assert (skills_root / "工程" / "SKILL.md").read_text(encoding="utf-8") == (
        "# Unicode skill\n"
    )
