"""Tests for astrbot/core/computer module.

This module tests the local booter, filesystem operations, Python execution,
shell execution, security restrictions, and the runtime-owned local client.
"""

import shlex
import sys
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.computer.booters.local import (
    LocalBooter,
    LocalFileSystemComponent,
    LocalPythonComponent,
    LocalShellComponent,
    _is_safe_command,
)
from astrbot.core.computer.computer_client import ComputerRuntime


class TestLocalBooterInit:
    """Tests for LocalBooter initialization."""

    def test_local_booter_init(self):
        """Test LocalBooter initializes with all components."""
        booter = LocalBooter()
        assert isinstance(booter, ComputerBooter)
        assert isinstance(booter.fs, LocalFileSystemComponent)
        assert isinstance(booter.python, LocalPythonComponent)
        assert isinstance(booter.shell, LocalShellComponent)

    def test_local_booter_properties(self):
        """Test LocalBooter properties return correct components."""
        booter = LocalBooter()
        assert booter.fs is booter._fs
        assert booter.python is booter._python
        assert booter.shell is booter._shell


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _shell_command(args: list[str]) -> str:
    if sys.platform == "win32":
        executable, *rest = args
        quoted_rest = " ".join(_powershell_quote(arg) for arg in rest)
        # PowerShell needs the call operator (&) for quoted, space-containing
        # executables; POSIX shells take the plain quoted form.
        return f"& {_powershell_quote(executable)} {quoted_rest}".rstrip()
    return shlex.join(args)


class TestLocalBooterLifecycle:
    """Tests for LocalBooter boot and shutdown."""

    @pytest.mark.asyncio
    async def test_boot(self):
        """Test LocalBooter boot method."""
        booter = LocalBooter()
        # Should not raise any exception
        await booter.boot("test-session-id")
        # boot is a no-op for LocalBooter

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Test LocalBooter shutdown method."""
        booter = LocalBooter()
        # Should not raise any exception
        await booter.shutdown()

    @pytest.mark.asyncio
    async def test_available(self):
        """Test LocalBooter available method returns True."""
        booter = LocalBooter()
        assert await booter.available() is True


class TestSecurityRestrictions:
    """Tests for security restrictions in LocalBooter."""

    def test_is_safe_command_allowed(self):
        """Test safe commands are allowed."""
        allowed_commands = [
            "echo hello",
            "ls -la",
            "pwd",
            "cat file.txt",
            "python script.py",
            "git status",
            "npm install",
            "pip list",
        ]
        for cmd in allowed_commands:
            assert _is_safe_command(cmd) is True, f"Command '{cmd}' should be allowed"

    def test_is_safe_command_blocked(self):
        """Test dangerous commands are blocked."""
        blocked_commands = [
            "rm -rf /",
            "rm -rf /tmp",
            "rm -fr /home",
            "mkfs.ext4 /dev/sda",
            "dd if=/dev/zero of=/dev/sda",
            "shutdown now",
            "reboot",
            "poweroff",
            "halt",
            "sudo rm",
            ":(){:|:&};:",
            "kill -9 -1",
            "killall python",
        ]
        for cmd in blocked_commands:
            assert _is_safe_command(cmd) is False, f"Command '{cmd}' should be blocked"

    def test_is_safe_command_blocks_whitespace_bypass_variants(self):
        """Test dangerous commands stay blocked with whitespace variations."""
        blocked_commands = [
            "rm\t-rf /",
            "rm    -r /tmp",
            "sudo\tpython script.py",
            "echo ok && rm\t-rf /",
            "kill\t-9 1",
        ]
        for cmd in blocked_commands:
            assert _is_safe_command(cmd) is False, f"Command '{cmd}' should be blocked"


class TestLocalShellComponent:
    """Tests for LocalShellComponent."""

    @pytest.mark.asyncio
    async def test_exec_safe_command(self):
        """Test executing a safe command."""
        shell = LocalShellComponent()
        result = await shell.exec("echo hello")
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_exec_blocked_command(self):
        """Test executing a blocked command raises PermissionError."""
        shell = LocalShellComponent()
        with pytest.raises(PermissionError) as exc_info:
            await shell.exec("rm -rf /")
        assert "Blocked unsafe shell command" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_exec_with_timeout(self):
        """Test command with timeout."""
        shell = LocalShellComponent()
        # Sleep command should complete within timeout
        result = await shell.exec("echo test", timeout_seconds=5)
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_with_cwd(self, tmp_path):
        """Test command execution with custom working directory."""
        shell = LocalShellComponent()
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            # Use python to read file to avoid Windows vs Unix command differences
            command = _shell_command(
                [sys.executable, "-c", f"print(open(r'{test_file}').read())"]
            )
            result = await shell.exec(
                command,
                cwd=str(tmp_path),
            )
            assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exec_with_env(self):
        """Test command execution with custom environment variables."""
        shell = LocalShellComponent()
        command = _shell_command(
            [sys.executable, "-c", 'import os; print(os.environ.get("TEST_VAR", ""))']
        )
        result = await shell.exec(
            command,
            env={"TEST_VAR": "test_value"},
        )
        assert result["exit_code"] == 0
        assert "test_value" in result["stdout"]


class TestLocalPythonComponent:
    """Tests for LocalPythonComponent."""

    @pytest.mark.asyncio
    async def test_exec_simple_code(self):
        """Test executing simple Python code."""
        python = LocalPythonComponent()
        result = await python.exec("print('hello')")
        assert result["data"]["output"]["text"].replace("\r\n", "\n") == "hello\n"

    @pytest.mark.asyncio
    async def test_exec_with_error(self):
        """Test executing Python code with error."""
        python = LocalPythonComponent()
        result = await python.exec("raise ValueError('test error')")
        assert "test error" in result["data"]["error"]

    @pytest.mark.asyncio
    async def test_exec_with_timeout(self):
        """Test Python execution with timeout."""
        python = LocalPythonComponent()
        # This should timeout
        result = await python.exec("import time; time.sleep(10)", timeout_seconds=1)
        assert "timed out" in result["data"]["error"].lower()

    @pytest.mark.asyncio
    async def test_exec_silent_mode(self):
        """Test Python execution in silent mode."""
        python = LocalPythonComponent()
        result = await python.exec("print('hello')", silent=True)
        assert result["data"]["output"]["text"] == ""

    @pytest.mark.asyncio
    async def test_exec_return_value(self):
        """Test Python execution returns value correctly."""
        python = LocalPythonComponent()
        result = await python.exec("result = 1 + 1\nprint(result)")
        assert "2" in result["data"]["output"]["text"]


class TestLocalFileSystemComponent:
    """Tests for LocalFileSystemComponent."""

    @pytest.mark.asyncio
    async def test_create_file(self, tmp_path):
        """Test creating a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.create_file(str(test_path), "test content")
            assert result["success"] is True
            assert test_path.exists()
            assert test_path.read_text() == "test content"

    @pytest.mark.asyncio
    async def test_read_file(self, tmp_path):
        """Test reading a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"
        test_path.write_text("test content")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.read_file(str(test_path))
            assert result["success"] is True
            assert result["content"] == "test content"

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_path):
        """Test writing to a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.write_file(str(test_path), "new content")
            assert result["success"] is True
            assert test_path.read_text() == "new content"

    @pytest.mark.asyncio
    async def test_delete_file(self, tmp_path):
        """Test deleting a file."""
        fs = LocalFileSystemComponent()
        test_path = tmp_path / "test.txt"
        test_path.write_text("test")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.delete_file(str(test_path))
            assert result["success"] is True
            assert not test_path.exists()

    @pytest.mark.asyncio
    async def test_delete_directory(self, tmp_path):
        """Test deleting a directory."""
        fs = LocalFileSystemComponent()
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("test")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            result = await fs.delete_file(str(test_dir))
            assert result["success"] is True
            assert not test_dir.exists()

    @pytest.mark.asyncio
    async def test_list_dir(self, tmp_path):
        """Test listing directory contents."""
        fs = LocalFileSystemComponent()
        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / ".hidden").write_text("hidden")

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            # Without hidden files
            result = await fs.list_dir(str(tmp_path), show_hidden=False)
            assert result["success"] is True
            assert "file1.txt" in result["entries"]
            assert "file2.txt" in result["entries"]
            assert ".hidden" not in result["entries"]

            # With hidden files
            result = await fs.list_dir(str(tmp_path), show_hidden=True)
            assert ".hidden" in result["entries"]

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tmp_path):
        """Test reading a non-existent file raises error."""
        fs = LocalFileSystemComponent()

        with (
            patch(
                "astrbot.core.computer.booters.local.get_astrbot_root",
                return_value=str(tmp_path),
            ),
        ):
            # Should raise FileNotFoundError
            with pytest.raises(FileNotFoundError):
                await fs.read_file(str(tmp_path / "nonexistent.txt"))


class TestComputerBooterBase:
    """Tests for ComputerBooter base class interface."""

    def test_base_class_is_protocol(self):
        """Test ComputerBooter has expected interface."""
        booter = LocalBooter()
        assert hasattr(booter, "fs")
        assert hasattr(booter, "python")
        assert hasattr(booter, "shell")
        assert hasattr(booter, "boot")
        assert hasattr(booter, "shutdown")
        assert hasattr(booter, "available")


class TestComputerRuntime:
    """Tests for the runtime-owned local computer client."""

    def test_get_local_booter(self):
        """A runtime reuses its own local booter without sharing globally."""
        runtime = ComputerRuntime()

        booter1 = runtime.get_local_booter()
        booter2 = runtime.get_local_booter()

        assert isinstance(booter1, LocalBooter)
        assert booter1 is booter2
        assert booter1 is not ComputerRuntime().get_local_booter()

    @pytest.mark.asyncio
    async def test_terminate_shuts_down_and_rejects_later_use(self):
        runtime = ComputerRuntime()
        booter = runtime.get_local_booter()
        booter.shutdown = AsyncMock()

        await runtime.terminate()

        booter.shutdown.assert_awaited_once()
        with pytest.raises(RuntimeError, match="terminated"):
            runtime.get_local_booter()
