"""Copied from astrbot.core.utils.version_comparator"""

import re
from itertools import zip_longest
from typing import cast

_SEMVER_RE = re.compile(
    r"^([0-9]+(?:\.[0-9]+)*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+(.+))?$"
)


class VersionComparator:
    @staticmethod
    def compare_version(v1: str, v2: str) -> int:
        """Compare version numbers according to Semver semantics. Supports version numbers with more than 3 digits and handles pre-release tags.

        Reference: https://semver.org/

        Returns 1 if v1 > v2, -1 if v1 < v2, 0 if v1 == v2.
        """
        normalized_v1 = VersionComparator._normalize_version(v1)
        normalized_v2 = VersionComparator._normalize_version(v2)
        v1_parts, v1_prerelease = VersionComparator._split_version(normalized_v1)
        v2_parts, v2_prerelease = VersionComparator._split_version(normalized_v2)

        numeric_comparison = VersionComparator._compare_numeric_parts(
            v1_parts, v2_parts
        )
        if numeric_comparison != 0:
            return numeric_comparison
        return VersionComparator._compare_prerelease(v1_prerelease, v2_prerelease)

    @staticmethod
    def _normalize_version(version: str) -> str:
        return version.lower().replace("v", "")

    @staticmethod
    def _split_version(version: str) -> tuple[list[int], list[int | str] | None]:
        match = _SEMVER_RE.match(version)
        if not match:
            return [], None

        numeric_parts = [int(part) for part in match.group(1).split(".")]
        prerelease = VersionComparator._split_prerelease(match.group(2))
        return numeric_parts, prerelease

    @staticmethod
    def _compare_numeric_parts(v1_parts: list[int], v2_parts: list[int]) -> int:
        for part1, part2 in zip_longest(v1_parts, v2_parts, fillvalue=0):
            if part1 > part2:
                return 1
            if part1 < part2:
                return -1
        return 0

    @staticmethod
    def _compare_prerelease(
        v1_prerelease: list[int | str] | None,
        v2_prerelease: list[int | str] | None,
    ) -> int:
        if v1_prerelease is None:
            return 0 if v2_prerelease is None else 1
        if v2_prerelease is None:
            return -1

        for part1, part2 in zip_longest(v1_prerelease, v2_prerelease):
            comparison = VersionComparator._compare_prerelease_part(part1, part2)
            if comparison != 0:
                return comparison
        return 0

    @staticmethod
    def _compare_prerelease_part(
        part1: int | str | None,
        part2: int | str | None,
    ) -> int:
        if part1 == part2:
            return 0
        if part1 is None:
            return -1
        if part2 is None:
            return 1
        part1_is_int = isinstance(part1, int)
        if part1_is_int != isinstance(part2, int):
            return -1 if part1_is_int else 1
        if part1_is_int:
            return 1 if cast("int", part1) > cast("int", part2) else -1
        return 1 if cast("str", part1) > cast("str", part2) else -1

    @staticmethod
    def _split_prerelease(prerelease: str | None) -> list[int | str] | None:
        if not prerelease:
            return None
        return [int(part) if part.isdigit() else part for part in prerelease.split(".")]
