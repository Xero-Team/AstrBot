"""Normalize CRLF and lone CR to LF in tracked text files."""

from __future__ import annotations

import subprocess
from pathlib import Path


def normalize_line_endings(repo_root: Path) -> list[str]:
    """Normalize existing tracked text files below ``repo_root`` to LF."""
    changed_files: list[str] = []
    entries = subprocess.run(
        ["git", "ls-files", "--eol"],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    for entry in entries:
        metadata, separator, relative_path = entry.partition("\t")
        if not separator or "attr/text" not in metadata:
            continue
        path = repo_root / relative_path
        if not path.is_file():
            continue
        content = path.read_bytes()
        normalized = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if content != normalized:
            path.write_bytes(normalized)
            changed_files.append(relative_path)
    return changed_files


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    changed_files = normalize_line_endings(repo_root)
    if changed_files:
        print(f"Normalized {len(changed_files)} tracked text file(s) to LF:")
        print(*(f"  {path}" for path in changed_files), sep="\n")
    else:
        print("All tracked text files already use LF.")


if __name__ == "__main__":
    main()
