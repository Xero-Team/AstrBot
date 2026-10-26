"""Deny policy enforcement in Local file and grep tools."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.auth.models import Role
from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.computer_client import ComputerRuntime
from astrbot.core.computer.process_sandbox import SandboxRunResult, SandboxSpec
from astrbot.core.tools.computer_tools import fs as fs_tools
from astrbot.core.tools.computer_tools import util as computer_util
from tests.fixtures.auth import attach_authorized_tool_context


def _context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    scope: str,
    deny_read: tuple[str, ...] = (),
    deny_write: tuple[str, ...] = (),
    network_mode: str = "off",
    allowed_domains: tuple[str, ...] = (),
    umo: str = "qq:friend:policy-user",
) -> tuple[ContextWrapper, Path, ComputerRuntime]:
    workspaces = tmp_path / "workspaces"
    skills = tmp_path / "skills"
    plugins = tmp_path / "plugins"
    temp = tmp_path / "temp"
    for directory in (workspaces, skills, plugins, temp):
        directory.mkdir()
    monkeypatch.setattr(
        computer_util, "get_astrbot_workspaces_path", lambda: str(workspaces)
    )
    monkeypatch.setattr(fs_tools, "get_astrbot_skills_path", lambda: str(skills))
    monkeypatch.setattr(fs_tools, "get_astrbot_plugin_path", lambda: str(plugins))
    monkeypatch.setattr(computer_util, "get_astrbot_temp_path", lambda: str(temp))
    monkeypatch.setattr(local_booter, "get_astrbot_system_tmp_path", lambda: str(temp))
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.util.get_process_sandbox_status",
        lambda: {"status": "detected", "backend": "bubblewrap"},
    )
    workspace = workspaces / computer_util.normalize_umo_for_workspace(umo)
    workspace.mkdir()
    runtime = ComputerRuntime()
    config = {
        "provider_settings": {
            "computer_use_runtime": "local",
            "computer_use_local_permissions": {
                "admin": {
                    "allow_execution": True,
                    "filesystem_scope": scope,
                    "network": {
                        "mode": network_mode,
                        "allowed_domains": list(allowed_domains),
                        "denied_domains": [],
                        "allow_private_network": True,
                        "allow_loopback": True,
                    },
                    "filesystem": {
                        "deny_read": list(deny_read),
                        "deny_write": list(deny_write),
                    },
                    "unix_sockets": {"mode": "deny", "allowed_paths": []},
                }
            },
        }
    }
    config_holder = SimpleNamespace(
        get_config=lambda **_kwargs: config,
        computer_runtime=runtime,
    )
    event = SimpleNamespace(
        unified_msg_origin=umo,
        get_sender_id=lambda: "policy-user",
    )
    attach_authorized_tool_context(
        event,
        config_holder,
        "tool.file_read",
        "tool.file_write",
        "tool.local_exec",
        effective_role=Role.INSTANCE_OPERATOR,
    )
    context = ContextWrapper(
        context=SimpleNamespace(context=config_holder, event=event),
        tool_call_timeout=30,
    )
    return context, workspace, runtime


@pytest.mark.asyncio
async def test_read_write_and_edit_reject_denied_paths_before_creation(
    monkeypatch, tmp_path
) -> None:
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    secret = secret_dir / "token"
    secret.write_text("TOPSECRET", encoding="utf-8")
    context, _workspace, runtime = _context(
        monkeypatch,
        tmp_path,
        scope="host",
        deny_read=(str(secret_dir),),
        deny_write=(str(secret_dir),),
    )
    try:
        read = await fs_tools.FileReadTool().call(context, path=str(secret))
        assert "Access denied" in read
        assert "TOPSECRET" not in read
        write = await fs_tools.FileWriteTool().call(
            context, path=str(secret_dir / "new" / "file.txt"), content="x"
        )
        assert "Access denied" in write
        assert not (secret_dir / "new").exists()
        edit = await fs_tools.FileEditTool().call(
            context, path=str(secret), old="TOP", new="BOTTOM"
        )
        assert "Access denied" in edit
        assert secret.read_text() == "TOPSECRET"
    finally:
        await runtime.terminate()


@pytest.mark.asyncio
async def test_denied_symlink_target_is_rejected(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    context, workspace, runtime = _context(
        monkeypatch,
        tmp_path,
        scope="host",
        deny_read=(str(secret),),
    )
    link = workspace / "alias"
    link.symlink_to(secret)
    try:
        result = await fs_tools.FileReadTool().call(context, path=str(link))
        assert "Access denied" in result
        assert "TOPSECRET" not in result
    finally:
        await runtime.terminate()


@pytest.mark.asyncio
async def test_no_denies_preserves_host_reads(monkeypatch, tmp_path) -> None:
    target = tmp_path / "visible.txt"
    target.write_text("visible", encoding="utf-8")
    context, _workspace, runtime = _context(monkeypatch, tmp_path, scope="host")
    try:
        result = await fs_tools.FileReadTool().call(context, path=str(target))
        assert "visible" in result
    finally:
        await runtime.terminate()


@pytest.mark.asyncio
async def test_grep_with_denies_uses_complete_sandbox_spec(
    monkeypatch, tmp_path
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    context, workspace, runtime = _context(
        monkeypatch,
        tmp_path,
        scope="host",
        deny_read=(str(secret),),
        network_mode="allowlist",
        allowed_domains=("example.com",),
    )
    captured: list[SandboxSpec] = []

    class FakeSandbox:
        def run(self, argv, spec, **kwargs):
            captured.append(spec)
            return SandboxRunResult(
                returncode=0,
                stdout=f"{workspace}/safe.txt:1:needle\n".encode(),
                stderr=b"",
            )

    monkeypatch.setattr(local_booter.shutil, "which", lambda _name: "/usr/bin/rg")
    monkeypatch.setattr(local_booter, "create_process_sandbox", lambda: FakeSandbox())
    try:
        result = await fs_tools.GrepTool().call(
            context,
            pattern="needle",
            path=str(workspace),
        )
        assert "needle" in result
        assert captured
        spec = captured[0]
        assert spec.policy.filesystem.deny_read == (secret.as_posix(),)
        assert spec.policy.network.mode == "off"
        assert spec.policy.unix_sockets.mode == "deny"
        assert spec.workspace == workspace.resolve()
    finally:
        await runtime.terminate()


@pytest.mark.asyncio
async def test_grep_missing_backend_fails_closed(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    context, workspace, runtime = _context(
        monkeypatch,
        tmp_path,
        scope="host",
        deny_read=(str(secret),),
    )
    monkeypatch.setattr(local_booter.shutil, "which", lambda _name: None)
    try:
        result = await fs_tools.GrepTool().call(
            context,
            pattern="needle",
            path=str(workspace),
        )
        assert "Error searching files" in result
        assert "unavailable" in result
    finally:
        await runtime.terminate()


@pytest.mark.asyncio
async def test_grep_missing_sandbox_backend_fails_closed(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    context, workspace, runtime = _context(
        monkeypatch,
        tmp_path,
        scope="host",
        deny_read=(str(secret),),
    )
    monkeypatch.setattr(local_booter.shutil, "which", lambda _name: "/usr/bin/rg")

    def unavailable():
        raise RuntimeError("sandbox backend unavailable")

    monkeypatch.setattr(local_booter, "create_process_sandbox", unavailable)
    try:
        result = await fs_tools.GrepTool().call(
            context,
            pattern="needle",
            path=str(workspace),
        )
        assert "Error searching files" in result
        assert "unavailable" in result
    finally:
        await runtime.terminate()


@pytest.mark.asyncio
async def test_host_writes_and_edits_use_descriptors_when_denies_exist(
    monkeypatch, tmp_path
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    allowed = tmp_path / "allowed" / "note.txt"
    context, _workspace, runtime = _context(
        monkeypatch,
        tmp_path,
        scope="host",
        deny_write=(str(secret),),
    )
    try:
        write = await fs_tools.FileWriteTool().call(
            context, path=str(allowed), content="hello"
        )
        assert "successfully" in write
        assert allowed.read_text() == "hello"
        edit = await fs_tools.FileEditTool().call(
            context, path=str(allowed), old="hello", new="world"
        )
        assert "Edited" in edit
        assert allowed.read_text() == "world"
        assert secret.read_text() == "TOPSECRET"
    finally:
        await runtime.terminate()


@pytest.mark.asyncio
async def test_glob_matched_directory_deny_covers_descendants_in_file_tools(
    monkeypatch, tmp_path
) -> None:
    secret_dir = tmp_path / "secrets"
    nested = secret_dir / "nested"
    nested.mkdir(parents=True)
    secret = nested / "token"
    secret.write_text("TOPSECRET", encoding="utf-8")
    context, _workspace, runtime = _context(
        monkeypatch,
        tmp_path,
        scope="host",
        deny_read=(str(tmp_path / "secret*"),),
    )
    try:
        read = await fs_tools.FileReadTool().call(context, path=str(secret))
        assert "Access denied" in read
        assert "TOPSECRET" not in read
    finally:
        await runtime.terminate()
