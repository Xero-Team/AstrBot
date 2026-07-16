"""Run a repository-local Node tool over tracked files in bounded batches."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> tuple[str, list[str], list[str]]:
    if len(sys.argv) < 4 or "--" not in sys.argv[2:]:
        raise SystemExit(
            "Usage: run_tracked_node_tool.py <tool> --pattern <glob> [--pattern <glob> ...] -- <tool arguments>"
        )

    tool = sys.argv[1]
    divider = sys.argv.index("--", 2)
    pattern_args = sys.argv[2:divider]
    tool_args = sys.argv[divider + 1 :]
    patterns: list[str] = []
    while pattern_args:
        if len(pattern_args) < 2 or pattern_args[0] != "--pattern":
            raise SystemExit("Patterns must be provided as '--pattern <glob>'.")
        patterns.append(pattern_args[1])
        pattern_args = pattern_args[2:]
    if not patterns:
        raise SystemExit("At least one '--pattern <glob>' is required.")
    return tool, patterns, tool_args


def tracked_files(repo_root: Path, patterns: list[str]) -> list[str]:
    """Return existing tracked files that match the requested patterns."""
    files = subprocess.run(
        ["git", "ls-files", "-z", "--", *patterns],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    return [
        path.decode()
        for path in files
        if path and (repo_root / path.decode()).is_file()
    ]


def main() -> None:
    tool, patterns, tool_args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    executable = f"{tool}.cmd" if os.name == "nt" else tool
    tool_path = repo_root / "node_modules" / ".bin" / executable
    if not tool_path.is_file():
        raise SystemExit(
            f"Node tool '{tool}' is not installed. Run 'make bootstrap' first."
        )

    files = tracked_files(repo_root, patterns)
    for index in range(0, len(files), 64):
        subprocess.run(
            [str(tool_path), *tool_args, *files[index : index + 64]],
            cwd=repo_root,
            check=True,
        )


if __name__ == "__main__":
    main()
