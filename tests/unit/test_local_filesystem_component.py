from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from astrbot.core.computer import process_sandbox
from astrbot.core.computer.booters import local as local_booter
from astrbot.core.computer.booters.local import LocalFileSystemComponent


def _allow_tmp_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local_booter, "get_astrbot_root", lambda: str(tmp_path))


def test_local_file_system_component_prefers_utf8_before_windows_locale(
    monkeypatch,
    tmp_path: Path,
):
    _allow_tmp_root(monkeypatch, tmp_path)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp936",
    )

    skill_path = tmp_path / "skills" / "demo.txt"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_bytes("技能内容".encode())

    result = asyncio.run(LocalFileSystemComponent().read_file(str(skill_path)))

    assert result["success"] is True
    assert result["content"] == "技能内容"


def test_local_file_system_component_falls_back_to_gbk_on_windows(
    monkeypatch,
    tmp_path: Path,
):
    _allow_tmp_root(monkeypatch, tmp_path)
    monkeypatch.setattr(local_booter.os, "name", "nt", raising=False)
    monkeypatch.setattr(
        local_booter.locale,
        "getpreferredencoding",
        lambda _do_setlocale=False: "cp1252",
    )

    skill_path = tmp_path / "skills" / "weibo-hot.txt"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_bytes("微博热搜".encode("gbk"))

    result = asyncio.run(LocalFileSystemComponent().read_file(str(skill_path)))

    assert result["success"] is True
    assert result["content"] == "微博热搜"


def test_local_file_system_component_applies_requested_mode_to_unicode_path(
    monkeypatch,
    tmp_path: Path,
):
    """Creating a file keeps the requested permission policy on Windows paths."""
    _allow_tmp_root(monkeypatch, tmp_path)
    target = tmp_path / "含 空格" / "notes.txt"
    chmod_calls = []

    def record_chmod(path: str, mode: int) -> None:
        chmod_calls.append((Path(path), mode))

    monkeypatch.setattr(local_booter.os, "chmod", record_chmod)

    result = asyncio.run(
        LocalFileSystemComponent().create_file(
            str(target),
            "content",
            mode=0o600,
        )
    )

    assert result == {"success": True, "path": str(target.resolve())}
    assert target.read_text(encoding="utf-8") == "content"
    assert chmod_calls == [(target.resolve(), 0o600)]


def test_local_file_system_component_searches_with_rg_glob_and_context(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b"src\\demo.py:4:needle\n",
            stderr=b"",
        )

    monkeypatch.setattr(
        local_booter.shutil,
        "which",
        lambda _executable: r"C:\tools\rg.exe",
    )
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(local_booter.subprocess, "run", fake_run)

    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            "needle",
            path=r"C:\workspace",
            glob="*.py",
            after_context=2,
            before_context=1,
        )
    )

    assert result == {"success": True, "content": "src\\demo.py:4:needle\n"}
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:6] == [
        r"C:\tools\rg.exe",
        "--color=never",
        "-n",
        "--max-columns",
        "1000",
        "-e",
    ]
    assert command[6:11] == ["needle", "-g", "*.py", "-A", "2"]
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 30


def test_local_file_system_component_treats_rg_no_match_as_success(monkeypatch):
    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: "/bin/rg")
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(
        local_booter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=b"",
        ),
    )

    result = asyncio.run(LocalFileSystemComponent().search_files("missing"))

    assert result == {"success": True, "content": ""}


def test_local_file_system_component_truncates_rg_long_lines_after_search(
    monkeypatch,
):
    long_line = b"result.py:1:" + (b"x" * 1200) + b"\n"
    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: "/bin/rg")
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(
        local_booter.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout=long_line,
            stderr=b"",
        ),
    )

    result = asyncio.run(LocalFileSystemComponent().search_files("x"))

    assert result["success"] is True
    assert result["content"] == long_line.decode()[:1000] + "\n"


def test_local_file_system_component_falls_back_without_rg(monkeypatch, tmp_path: Path):
    _allow_tmp_root(monkeypatch, tmp_path)
    target = tmp_path / "target.txt"
    target.write_text("needle in haystack\n", encoding="utf-8")
    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: None)

    result = asyncio.run(
        LocalFileSystemComponent().search_files("needle", path=str(target))
    )

    assert result["success"] is True
    assert "needle in haystack" in result["content"]


def test_local_file_system_component_runs_restricted_search_in_read_only_sandbox(
    monkeypatch,
    tmp_path,
):
    sandbox_calls = []

    class FakeSandbox:
        def run(self, argv, spec, *, env=None, timeout=None, **kwargs):
            sandbox_calls.append(
                {
                    "argv": argv,
                    "workspace": spec.workspace,
                    "env": env,
                    "workspace_writable": spec.workspace_writable,
                    "timeout": timeout,
                    "kwargs": kwargs,
                }
            )
            return process_sandbox.SandboxRunResult(
                returncode=0,
                stdout=b"target.txt:1:needle\n",
                stderr=b"",
            )

    rg_executable = r"C:\tools\rg.exe" if os.name == "nt" else "/usr/bin/rg"
    monkeypatch.setattr(local_booter.shutil, "which", lambda _name: rg_executable)
    monkeypatch.setattr(
        local_booter,
        "create_process_sandbox",
        lambda: FakeSandbox(),
    )

    result = asyncio.run(
        LocalFileSystemComponent().search_files(
            "needle",
            path=str(tmp_path / "target.txt"),
            sandboxed=True,
            sandbox_root=str(tmp_path),
        )
    )

    expected_search_command = [
        str(Path(rg_executable).resolve()),
        "--color=never",
        "-n",
        "--max-columns",
        "1000",
        "-e",
        "needle",
        "--",
        str(tmp_path / "target.txt"),
    ]
    assert result == {"success": True, "content": "target.txt:1:needle\n"}
    assert sandbox_calls == [
        {
            "argv": expected_search_command,
            "workspace": tmp_path,
            "env": None,
            "workspace_writable": False,
            "timeout": 30,
            "kwargs": {},
        }
    ]


def test_local_file_system_component_handles_search_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(local_booter.shutil, "which", lambda _executable: "/bin/rg")
    monkeypatch.setattr(local_booter.sys, "version_info", (3, 14))
    monkeypatch.setattr(local_booter.subprocess, "run", fake_run)

    result = asyncio.run(LocalFileSystemComponent().search_files("needle"))

    assert result == {
        "success": False,
        "content": "",
        "error": "File search timed out after 30 seconds.",
    }
