from pathlib import Path

from astrbot.cli.utils.basic import get_astrbot_root


def test_get_astrbot_root_uses_cwd_when_env_is_unset(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ASTRBOT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    assert get_astrbot_root() == tmp_path.resolve()


def test_get_astrbot_root_honors_astrbot_root_over_cwd(monkeypatch, tmp_path: Path):
    env_root = tmp_path / "from-env"
    cwd_root = tmp_path / "from-cwd"
    env_root.mkdir()
    cwd_root.mkdir()
    monkeypatch.setenv("ASTRBOT_ROOT", str(env_root))
    monkeypatch.chdir(cwd_root)

    assert get_astrbot_root() == env_root.resolve()
