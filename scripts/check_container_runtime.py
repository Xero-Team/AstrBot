#!/usr/bin/env python3
"""Verify commands promised by an already-built AstrBot runtime image."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

FEATURES = frozenset(
    {"browser", "documents", "media", "ocr", "fonts", "node", "docker"}
)
FULL_FEATURES = frozenset(FEATURES)

BASE_CHECKS = (
    ("Python application", "python -c 'import astrbot'"),
    ("uv", "uv --version"),
    ("uvx", "uvx --version"),
    (
        "uvx child process",
        "python -c \"import subprocess; subprocess.run(['uvx', '--version'], check=True)\"",
    ),
)

FEATURE_CHECKS: dict[str, tuple[tuple[str, str], ...]] = {
    "browser": (
        ("Playwright", "playwright --version"),
        (
            "Chromium assets",
            'test -d "$PLAYWRIGHT_BROWSERS_PATH" && test -n "$(ls -A "$PLAYWRIGHT_BROWSERS_PATH")"',
        ),
    ),
    "documents": (
        ("Pandoc", "pandoc --version"),
        ("Poppler", "pdftotext -v"),
        ("XeLaTeX", "xelatex --version"),
    ),
    "media": (("FFmpeg", "ffmpeg -version"), ("FFprobe", "ffprobe -version")),
    "ocr": (
        (
            "Tesseract languages",
            "tesseract --list-langs | grep -Fx eng && tesseract --list-langs | grep -Fx chi_sim",
        ),
    ),
    "fonts": (("CJK font", "fc-match 'Noto Sans CJK SC'"),),
    "node": (
        (
            "Node launchers",
            "node --version && npm --version && npx --version && pnpm --version",
        ),
        ("Codex", "codex --version"),
    ),
    "docker": (("Docker CLI", "docker --version && docker compose version"),),
}


def normalize_features(value: str) -> frozenset[str]:
    """Expand the Dockerfile's runtime feature argument."""
    if value == "full":
        return FULL_FEATURES
    if value == "minimal":
        return frozenset()
    features = frozenset(item.strip() for item in value.split(",") if item.strip())
    if not features or features - FEATURES:
        invalid = ", ".join(sorted(features - FEATURES)) or "an empty feature set"
        raise ValueError(f"unknown runtime feature: {invalid}")
    return features


def checks_for_features(features: frozenset[str]) -> tuple[tuple[str, str], ...]:
    """Return image checks in a stable order."""
    checks = list(BASE_CHECKS)
    for feature in sorted(features):
        checks.extend(FEATURE_CHECKS[feature])
    return tuple(checks)


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True)


def verify_image(image: str, features: frozenset[str]) -> None:
    """Run the selected checks in one temporary container per command."""
    inspect = _run(["docker", "image", "inspect", image])
    if inspect.returncode:
        detail = inspect.stderr.strip() or inspect.stdout.strip()
        raise RuntimeError(f"cannot inspect image {image!r}: {detail}")

    for name, check in checks_for_features(features):
        result = _run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "bash",
                image,
                "-o",
                "pipefail",
                "-c",
                check,
            ]
        )
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{name} check failed: {detail}")
        print(f"ok: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="already-built local image tag or ID"
    )
    parser.add_argument(
        "--features",
        required=True,
        help="full, minimal, or Dockerfile feature groups separated by commas",
    )
    args = parser.parse_args()
    try:
        verify_image(args.image, normalize_features(args.features))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"container runtime check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
