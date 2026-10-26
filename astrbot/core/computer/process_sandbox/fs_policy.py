"""Bounded launch-time filesystem deny expansion and mask planning."""

from __future__ import annotations

import atexit
import os
import shutil
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from astrbot.core.computer.local_policy import (
    LocalFilesystemPolicy,
    expand_path_rule,
    path_rule_matches,
)

MAX_DENY_MASKS = 1024
MAX_VISITED_DIRECTORIES = 10_000

Access = Literal["read", "write", "edit"]
MaskMode = Literal["read", "write"]

_MASK_SOURCE_DIR: Path | None = None
_EMPTY_MASK_FILE: Path | None = None
_MASK_LOCK = threading.Lock()


class DenyPolicyError(RuntimeError):
    """Raised when a deny rule cannot be enforced completely."""


@dataclass(frozen=True, slots=True)
class DenyMask:
    """One canonical target that must be masked after every grant."""

    target: Path
    mode: MaskMode
    is_directory: bool
    is_socket: bool = False


def _empty_mask_file() -> Path:
    global _MASK_SOURCE_DIR, _EMPTY_MASK_FILE
    with _MASK_LOCK:
        if _EMPTY_MASK_FILE is not None and _EMPTY_MASK_FILE.exists():
            return _EMPTY_MASK_FILE
        _MASK_SOURCE_DIR = Path(tempfile.mkdtemp(prefix="astrbot-deny-mask-"))
        empty = _MASK_SOURCE_DIR / "empty"
        empty.write_bytes(b"")
        os.chmod(empty, 0)
        _EMPTY_MASK_FILE = empty
        return empty


def _cleanup_mask_sources() -> None:
    global _MASK_SOURCE_DIR, _EMPTY_MASK_FILE
    with _MASK_LOCK:
        directory = _MASK_SOURCE_DIR
        _MASK_SOURCE_DIR = None
        _EMPTY_MASK_FILE = None
    if directory is not None:
        shutil.rmtree(directory, ignore_errors=True)


atexit.register(_cleanup_mask_sources)


def _is_glob_rule(rule: str) -> bool:
    return any(marker in rule for marker in ("*", "?", "["))


def _canonical(path: Path) -> Path:
    return Path(os.path.abspath(path))


class DenyRuleSet:
    """Policy-level matcher plus bounded, fail-closed launch expansion."""

    def __init__(self, policy: LocalFilesystemPolicy) -> None:
        """Store configured deny rules without creating any path."""
        self.policy = policy
        self.read_rules = tuple(policy.deny_read)
        self.write_rules = tuple(policy.deny_write)

    @property
    def empty(self) -> bool:
        """Return whether no deny rule is configured."""
        return not self.read_rules and not self.write_rules

    def _rules_for(self, access: Access) -> tuple[str, ...]:
        if access == "read":
            return self.read_rules
        if access == "write":
            return self.write_rules
        return tuple(dict.fromkeys((*self.read_rules, *self.write_rules)))

    def matches(self, path: Path, access: Access) -> bool:
        """Return whether an access is denied without touching the filesystem."""
        candidate = _canonical(path)
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            resolved = candidate
        for rule in self._rules_for(access):
            if _rule_matches(rule, candidate, resolved):
                return True
        return False

    def expand_for_launch(self) -> tuple[DenyMask, ...]:
        """Expand every rule at launch time or fail the whole launch.

        Raises:
            DenyPolicyError: If a literal target is missing, a glob exceeds its
                bounds, or a target type cannot be masked without exposing data.
        """
        masks: dict[tuple[str, MaskMode], DenyMask] = {}
        mode_rules: tuple[tuple[MaskMode, tuple[str, ...]], ...] = (
            ("read", self.read_rules),
            ("write", self.write_rules),
        )
        for mode, rules in mode_rules:
            for rule in rules:
                for target in _expand_rule(rule):
                    canonical = _canonical(target)
                    try:
                        info = canonical.lstat()
                    except FileNotFoundError as exc:
                        raise DenyPolicyError(
                            "A configured Local deny target no longer exists; "
                            "execution was blocked."
                        ) from exc
                    except OSError as exc:
                        raise DenyPolicyError(
                            "A configured Local deny target could not be inspected; "
                            "execution was blocked."
                        ) from exc
                    if stat.S_ISLNK(info.st_mode):
                        try:
                            canonical = canonical.resolve(strict=True)
                            info = canonical.lstat()
                        except OSError as exc:
                            raise DenyPolicyError(
                                "A configured Local deny symlink target is missing; "
                                "execution was blocked."
                            ) from exc
                    is_directory = stat.S_ISDIR(info.st_mode)
                    is_socket = stat.S_ISSOCK(info.st_mode)
                    if mode == "read" and not (
                        is_directory or stat.S_ISREG(info.st_mode)
                    ):
                        raise DenyPolicyError(
                            "A read-deny target has an unsupported file type; "
                            "execution was blocked."
                        )
                    if mode == "write" and not (
                        is_directory or stat.S_ISREG(info.st_mode) or is_socket
                    ):
                        raise DenyPolicyError(
                            "A write-deny target has an unsupported file type; "
                            "execution was blocked."
                        )
                    key = (str(canonical), mode)
                    masks[key] = DenyMask(
                        target=canonical,
                        mode=mode,
                        is_directory=is_directory,
                        is_socket=is_socket,
                    )
                    if len(masks) > MAX_DENY_MASKS:
                        raise DenyPolicyError(
                            "Configured Local deny rules expand beyond the launch "
                            "mask limit; execution was blocked."
                        )
        return tuple(masks.values())

    @staticmethod
    def bwrap_arguments(masks: tuple[DenyMask, ...]) -> list[str]:
        """Return bubblewrap options that apply every mask after all grants."""
        arguments: list[str] = []
        empty = _empty_mask_file()
        # Write masks run first so a read denial always wins when both rules
        # target the same path; a later read-only bind must never expose data.
        for mask in sorted(masks, key=lambda item: item.mode == "read"):
            target = str(mask.target)
            if mask.mode == "write":
                arguments.extend(("--ro-bind", target, target))
            elif mask.is_directory:
                arguments.extend(("--tmpfs", target))
            else:
                arguments.extend(("--ro-bind", str(empty), target))
        return arguments


def _rule_matches(rule: str, candidate: Path, resolved: Path) -> bool:
    expanded = Path(expand_path_rule(rule))
    if _is_glob_rule(rule):
        return path_rule_matches(rule, candidate) or path_rule_matches(rule, resolved)
    try:
        expanded_target = expanded.resolve(strict=False)
    except OSError:
        expanded_target = expanded
    for path in (candidate, resolved):
        for denied in (expanded, expanded_target):
            if path == denied or path.is_relative_to(denied):
                return True
    return False


def _expand_rule(rule: str) -> tuple[Path, ...]:
    expanded = Path(expand_path_rule(rule))
    if not _is_glob_rule(rule):
        if not expanded.exists():
            raise DenyPolicyError(
                "A configured Local deny target does not exist; execution was blocked."
            )
        try:
            return (expanded.resolve(strict=True),)
        except OSError as exc:
            raise DenyPolicyError(
                "A configured Local deny target could not be resolved; "
                "execution was blocked."
            ) from exc

    anchor = _literal_anchor(expanded)
    if anchor is None or not anchor.exists():
        raise DenyPolicyError(
            "A configured Local deny glob has no existing traversal anchor; "
            "execution was blocked."
        )
    if anchor.is_file():
        try:
            return (
                (anchor.resolve(strict=True),)
                if path_rule_matches(rule, anchor)
                else ()
            )
        except OSError as exc:
            raise DenyPolicyError("A Local deny target could not be resolved.") from exc

    matches: list[Path] = []
    visited = 0

    def walk_error(error: OSError) -> None:
        raise DenyPolicyError(
            "A configured Local deny glob encountered an unreadable traversal; "
            "execution was blocked."
        ) from error

    for root, directories, files in os.walk(
        anchor,
        followlinks=False,
        onerror=walk_error,
    ):
        visited += 1
        if visited > MAX_VISITED_DIRECTORIES:
            raise DenyPolicyError(
                "A configured Local deny glob exceeded its directory traversal "
                "limit; execution was blocked."
            )
        root_path = Path(root)
        for name in (*directories, *files):
            candidate = root_path / name
            if not path_rule_matches(rule, candidate):
                continue
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise DenyPolicyError(
                    "A configured Local deny glob matched an unreadable target; "
                    "execution was blocked."
                ) from exc
            matches.append(resolved)
            if len(matches) > MAX_DENY_MASKS:
                raise DenyPolicyError(
                    "A configured Local deny glob exceeded its mask limit; "
                    "execution was blocked."
                )
    return tuple(dict.fromkeys(matches))


def _literal_anchor(path: Path) -> Path | None:
    parts = path.parts
    literal: list[str] = []
    for part in parts:
        if any(marker in part for marker in ("*", "?", "[")):
            break
        literal.append(part)
    if not literal:
        return None
    if literal == ["/"]:
        return Path("/")
    return Path(*literal)


__all__ = (
    "DenyMask",
    "DenyPolicyError",
    "DenyRuleSet",
    "MAX_DENY_MASKS",
    "MAX_VISITED_DIRECTORIES",
)
