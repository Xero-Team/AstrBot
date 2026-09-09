#!/usr/bin/env python3
"""Render GitHub Release notes for the GHCR nightly image."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_IMAGE = "ghcr.io/xero-team/astrbot"


def render_notes(
    *,
    image: str,
    tags: list[str],
    sha: str,
    commits: list[str],
    mode: str,
) -> str:
    """Build Markdown notes with pull commands and the commit window.

    Args:
        image: GHCR image name without a tag.
        tags: Image tags that were pushed.
        sha: Full git object name that was built.
        commits: Commit subjects included in this nightly, oldest first.
        mode: ``schedule`` or ``dispatch``.

    Returns:
        Markdown suitable for ``gh release create --notes``.

    Raises:
        ValueError: ``mode`` is not supported or no tags were provided.
    """
    if mode not in {"schedule", "dispatch"}:
        raise ValueError(f"Unsupported nightly notes mode: {mode}")
    if not tags:
        raise ValueError("At least one image tag is required")

    pull_lines = [f"docker pull {image}:{tag}" for tag in tags]
    pull_block = "\n".join(pull_lines)
    rolling = "nightly" if "nightly" in tags else tags[0]
    if commits:
        commit_lines = "\n".join(f"- {item}" for item in commits)
    elif mode == "dispatch":
        commit_lines = (
            "No commit window is attached. This is a manual rebuild of the "
            f"current HEAD (`{sha}`)."
        )
    else:
        commit_lines = f"No commits were listed for this scheduled build of `{sha}`."

    return (
        "# Xero-Team/AstrBot nightly image\n"
        "\n"
        "This prerelease publishes the **Xero-Team fork** `runtime` image. "
        "It is not an upstream AstrBotDevs image. Repository Compose files "
        "still source-build `astrbot:local`; this image is an optional pull "
        "path for hosts that do not want to compile on the machine.\n"
        "\n"
        f"Built from `{sha}`.\n"
        "\n"
        "## Docker pull\n"
        "\n"
        "```bash\n"
        f"{pull_block}\n"
        "```\n"
        "\n"
        "## Compose\n"
        "\n"
        "Use the rolling tag in a host Compose file. Do not add `build:`:\n"
        "\n"
        "```yaml\n"
        "services:\n"
        "  astrbot:\n"
        f"    image: {image}:{rolling}\n"
        "```\n"
        "\n"
        "```bash\n"
        "docker compose pull astrbot\n"
        "docker compose up -d astrbot\n"
        "```\n"
        "\n"
        "The first GHCR package is private until a maintainer sets package "
        "visibility to public. Anonymous pulls fail until then.\n"
        "\n"
        "## Commits\n"
        "\n"
        f"{commit_lines}\n"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for nightly notes rendering."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument(
        "--tag",
        action="append",
        dest="tags",
        required=True,
        help="Image tag to mention; repeat for each pushed tag",
    )
    parser.add_argument("--sha", required=True)
    parser.add_argument("--mode", choices=("schedule", "dispatch"), required=True)
    parser.add_argument(
        "--commit",
        action="append",
        dest="commits",
        default=[],
        help="Commit subject line; repeat for each commit",
    )
    parser.add_argument("--commits-file", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def load_commits(args: argparse.Namespace) -> list[str]:
    """Collect commit subjects from flags and an optional file."""
    commits = list(args.commits)
    if args.commits_file is not None:
        text = args.commits_file.read_text(encoding="utf-8")
        commits.extend(line.strip() for line in text.splitlines() if line.strip())
    return commits


def main(argv: list[str] | None = None) -> int:
    """Write nightly release notes to stdout or ``--output``."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    notes = render_notes(
        image=args.image,
        tags=args.tags,
        sha=args.sha,
        commits=load_commits(args),
        mode=args.mode,
    )
    if args.output is not None:
        args.output.write_text(notes, encoding="utf-8")
    else:
        sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
