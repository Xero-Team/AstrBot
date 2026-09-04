import os
from pathlib import Path


def check_astrbot_root(path: str | Path) -> bool:
    """Check if the path is an AstrBot root directory"""
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists() or not path.is_dir():
        return False
    if not (path / ".astrbot").exists():
        return False
    return True


def get_astrbot_root() -> Path:
    """Return the CLI runtime root.

    ``ASTRBOT_ROOT`` relocates the root when set. Otherwise this is the
    current working directory. The CLI does not use the packaged Desktop
    home-directory default; that path belongs to the core helper.
    """
    if path := os.environ.get("ASTRBOT_ROOT"):
        return Path(path).resolve()
    return Path.cwd()
