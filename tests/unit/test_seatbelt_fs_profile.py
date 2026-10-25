"""Seatbelt filesystem deny ordering and literal escaping."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from astrbot.core.computer.local_policy import LocalFilesystemPolicy, LocalSandboxPolicy
from astrbot.core.computer.process_sandbox import SandboxSpec
from astrbot.core.computer.process_sandbox.seatbelt import SeatbeltProcessSandbox


def _profile(monkeypatch, tmp_path: Path, policy: LocalSandboxPolicy) -> str:
    monkeypatch.setattr(
        "astrbot.core.computer.process_sandbox.seatbelt.shutil.which",
        lambda _name, **_kwargs: "/usr/bin/sandbox-exec",
    )
    command = SeatbeltProcessSandbox().build_command(
        [sys.executable, "-c", "pass"],
        SandboxSpec(workspace=tmp_path, policy=policy),
    )
    return command[command.index("-p") + 1]


def test_deny_rules_follow_every_grant(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("value", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        filesystem=LocalFilesystemPolicy(
            deny_read=(str(secret),),
            deny_write=(str(secret),),
        ),
    )
    profile = _profile(monkeypatch, workspace, policy)
    read_deny = profile.index(f'(deny file-read* (literal "{secret.resolve()}"))')
    write_deny = profile.index(f'(deny file-write* (literal "{secret.resolve()}"))')
    workspace_grant = profile.index("(allow file-write*")
    assert read_deny > workspace_grant
    assert write_deny > workspace_grant


def test_directory_denies_use_subpath(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.mkdir()
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="host",
        filesystem=LocalFilesystemPolicy(deny_read=(str(secret),)),
    )
    profile = _profile(monkeypatch, tmp_path, policy)
    assert f'(deny file-read* (subpath "{secret.resolve()}"))' in profile


def test_missing_literal_fails_closed(monkeypatch, tmp_path: Path) -> None:
    policy = LocalSandboxPolicy(
        allow_execution=True,
        filesystem_scope="workspace",
        filesystem=LocalFilesystemPolicy(deny_read=(str(tmp_path / "missing"),)),
    )
    with pytest.raises(RuntimeError, match="does not exist"):
        _profile(monkeypatch, tmp_path, policy)
