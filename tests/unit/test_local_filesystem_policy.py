"""Bounded Local filesystem deny matching and launch mask planning."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from astrbot.core.computer.local_policy import LocalFilesystemPolicy
from astrbot.core.computer.process_sandbox.fs_policy import (
    MAX_VISITED_DIRECTORIES,
    DenyPolicyError,
    DenyRuleSet,
)


def test_deny_rule_set_matches_literal_descendants_and_symlink_targets(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "secret"
    secret.mkdir()
    target = secret / "token"
    target.write_text("value", encoding="utf-8")
    link = tmp_path / "alias"
    link.symlink_to(target)
    rules = DenyRuleSet(LocalFilesystemPolicy(deny_read=(str(secret),)))
    assert rules.matches(target, "read")
    assert rules.matches(secret / "unknown", "read")
    assert not rules.matches(secret, "write")
    link_rules = DenyRuleSet(LocalFilesystemPolicy(deny_write=(str(link),)))
    assert link_rules.matches(link, "write")
    assert link_rules.matches(target, "write")


def test_glob_expansion_is_canonical_and_deduplicated(tmp_path: Path) -> None:
    first = tmp_path / "one" / ".env"
    second = tmp_path / "two" / ".env"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("A", encoding="utf-8")
    second.write_text("B", encoding="utf-8")
    link = tmp_path / "one" / "linked.env"
    link.symlink_to(second)
    rules = DenyRuleSet(
        LocalFilesystemPolicy(deny_read=(str(tmp_path / "**" / ".env"),))
    )
    masks = rules.expand_for_launch()
    targets = {mask.target for mask in masks}
    assert first.resolve() in targets
    assert second.resolve() in targets
    assert len(masks) == len(targets)


def test_missing_literal_target_fails_closed(tmp_path: Path) -> None:
    rules = DenyRuleSet(LocalFilesystemPolicy(deny_read=(str(tmp_path / "missing"),)))
    with pytest.raises(DenyPolicyError, match="does not exist"):
        rules.expand_for_launch()


def test_glob_without_matches_is_allowed_but_requires_an_anchor(tmp_path: Path) -> None:
    rules = DenyRuleSet(
        LocalFilesystemPolicy(deny_read=(str(tmp_path / "**" / ".nomatch"),))
    )
    assert rules.expand_for_launch() == ()
    with pytest.raises(DenyPolicyError, match="traversal anchor"):
        DenyRuleSet(LocalFilesystemPolicy(deny_read=("**/.env",))).expand_for_launch()


def test_directory_read_masks_use_tmpfs_and_files_use_empty_file(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "secret-dir"
    directory.mkdir()
    file = tmp_path / "secret.txt"
    file.write_text("value", encoding="utf-8")
    rules = DenyRuleSet(
        LocalFilesystemPolicy(
            deny_read=(str(directory), str(file)),
            deny_write=(str(file),),
        )
    )
    masks = rules.expand_for_launch()
    arguments = DenyRuleSet.bwrap_arguments(masks)
    assert ["--tmpfs", str(directory)] == arguments[
        arguments.index("--tmpfs") : arguments.index("--tmpfs") + 2
    ]
    assert "--ro-bind" in arguments
    assert arguments.count(str(file)) >= 2


def test_special_file_types_fail_instead_of_partial_masking(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFOs are unavailable on this platform.")
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    rules = DenyRuleSet(LocalFilesystemPolicy(deny_read=(str(fifo),)))
    with pytest.raises(DenyPolicyError, match="unsupported"):
        rules.expand_for_launch()


def test_glob_traversal_limit_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.fs_policy.MAX_VISITED_DIRECTORIES",
        1,
    )
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "x.txt").write_text("x", encoding="utf-8")
    rules = DenyRuleSet(
        LocalFilesystemPolicy(deny_read=(str(tmp_path / "**" / "*.txt"),))
    )
    with pytest.raises(DenyPolicyError, match="directory traversal limit"):
        rules.expand_for_launch()
    assert MAX_VISITED_DIRECTORIES == 10_000


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows chmod does not make directories unreadable.",
)
def test_unreadable_traversal_fails_closed(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "value.txt").write_text("value", encoding="utf-8")
    blocked.chmod(0)
    try:
        rules = DenyRuleSet(
            LocalFilesystemPolicy(deny_read=(str(tmp_path / "**" / "*.txt"),))
        )
        with pytest.raises(DenyPolicyError, match="unreadable traversal"):
            rules.expand_for_launch()
    finally:
        blocked.chmod(0o700)
