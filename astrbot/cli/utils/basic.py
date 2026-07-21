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
    """Get the AstrBot root directory path"""
    return Path.cwd()
