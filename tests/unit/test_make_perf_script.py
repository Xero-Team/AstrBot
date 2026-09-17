from __future__ import annotations

import importlib.util
import os
import signal
import socket
import stat
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "make_perf.sh"

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="make perf is Linux-only"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_listen(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.connect(("127.0.0.1", port))
            except OSError:
                time.sleep(0.05)
                continue
            return
    raise AssertionError(f"server on port {port} did not start")


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_perf(
    env: dict[str, str],
    *,
    extra_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    command_env.update(env)
    if extra_path is not None:
        command_env["PATH"] = f"{extra_path}{os.pathsep}{command_env.get('PATH', '')}"
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=command_env,
    )


@pytest.fixture
def perf_home(tmp_path: Path) -> Path:
    (tmp_path / "bin").mkdir()
    (tmp_path / "out").mkdir()
    return tmp_path


@pytest.fixture
def python_http_server() -> Iterator[tuple[subprocess.Popen[str], int]]:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        _wait_for_listen(port)
        yield proc, port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _base_env(perf_home: Path, port: int, pid: int) -> dict[str, str]:
    pid_file = perf_home / "backend.pid"
    pid_file.write_text(f"{pid}\n", encoding="utf-8")
    return {
        "MODE": "cpu",
        "DURATION": "1",
        "ASTRBOT_DASHBOARD_PORT": str(port),
        "ASTRBOT_PERF_PID_FILE": str(pid_file),
        "ASTRBOT_PERF_OUTPUT_DIR": str(perf_home / "out"),
        "ASTRBOT_PERF_PYSPY_FROM": "py-spy>=0.4.2",
    }


def _fake_uvx_script(log_path: Path, output_text: str = "ok\n") -> str:
    return (
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        f"pathlib.Path({str(log_path)!r}).write_text(' '.join(sys.argv[1:]), encoding='utf-8')\n"
        "argv = sys.argv[1:]\n"
        "if '-o' in argv:\n"
        "    out = pathlib.Path(argv[argv.index('-o') + 1])\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        f"    out.write_text({output_text!r}, encoding='utf-8')\n"
    )


def _fake_uv_script(log_path: Path) -> str:
    return (
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "argv = sys.argv[1:]\n"
        f"path = pathlib.Path({str(log_path)!r})\n"
        "previous = path.read_text(encoding='utf-8') if path.exists() else ''\n"
        "path.write_text(previous + ' '.join(argv) + '\\n', encoding='utf-8')\n"
        "joined = ' '.join(argv)\n"
        "has_no_sync = '--no-sync' in argv\n"
        "if has_no_sync and 'python' in argv and 'import memray' in joined:\n"
        "    raise SystemExit(0)\n"
        "if has_no_sync and 'memray' in argv:\n"
        "    if '-o' in argv:\n"
        "        out = pathlib.Path(argv[argv.index('-o') + 1])\n"
        "        out.parent.mkdir(parents=True, exist_ok=True)\n"
        "        out.write_text('fake-memray\\n', encoding='utf-8')\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )


def _python_child_pid(parent_pid: int, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    children_file = Path(f"/proc/{parent_pid}/task/{parent_pid}/children")
    while time.monotonic() < deadline:
        if children_file.exists():
            children = children_file.read_text(encoding="utf-8").split()
            if children:
                return int(children[0])
        time.sleep(0.05)
    raise AssertionError(f"process {parent_pid} did not spawn a child")


def _stop_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        proc.wait(timeout=5)


def test_rejects_non_linux_kernel(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    proc, port = python_http_server
    uname = perf_home / "bin" / "uname"
    _write_executable(
        uname,
        "#!/usr/bin/env bash\nprintf 'Darwin\\n'\n",
    )
    result = _run_perf(
        _base_env(perf_home, port, proc.pid), extra_path=perf_home / "bin"
    )
    assert result.returncode == 2
    assert "Linux-only" in (result.stderr or "")


def test_rejects_unknown_mode(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    proc, port = python_http_server
    env = _base_env(perf_home, port, proc.pid)
    env["MODE"] = "trace"
    result = _run_perf(env)
    assert result.returncode == 2
    assert "Unsupported MODE" in (result.stderr or "")


def test_rejects_invalid_duration(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    proc, port = python_http_server
    env = _base_env(perf_home, port, proc.pid)
    env["DURATION"] = "0"
    result = _run_perf(env)
    assert result.returncode == 2
    assert "DURATION must be a positive integer" in (result.stderr or "")


def test_rejects_missing_backend(perf_home: Path) -> None:
    env = {
        "MODE": "cpu",
        "DURATION": "1",
        "ASTRBOT_DASHBOARD_PORT": str(_free_port()),
        "ASTRBOT_PERF_PID_FILE": str(perf_home / "missing.pid"),
        "ASTRBOT_PERF_OUTPUT_DIR": str(perf_home / "out"),
    }
    result = _run_perf(env)
    assert result.returncode == 2
    assert "Backend is not running" in (result.stderr or "")


def test_cpu_mode_records_flamegraph(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    proc, port = python_http_server
    log_path = perf_home / "uvx.log"
    _write_executable(
        perf_home / "bin" / "uvx",
        _fake_uvx_script(log_path, "fake-svg\n"),
    )
    result = _run_perf(
        _base_env(perf_home, port, proc.pid), extra_path=perf_home / "bin"
    )
    assert result.returncode == 0, result.stderr
    outputs = list((perf_home / "out").glob("cpu-*.svg"))
    assert len(outputs) == 1
    assert outputs[0].read_text(encoding="utf-8") == "fake-svg\n"
    recorded = log_path.read_text(encoding="utf-8")
    assert "py-spy" in recorded
    assert "record" in recorded
    assert f"--pid {proc.pid}" in recorded
    assert "--idle" not in recorded


def test_cpu_mode_walks_pid_file_to_python_child(perf_home: Path) -> None:
    listen_port = _free_port()
    unused_port = _free_port()
    parent = subprocess.Popen(
        [
            "bash",
            "-c",
            f"{sys.executable} -m http.server {listen_port} --bind 127.0.0.1 & wait",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    try:
        _wait_for_listen(listen_port)
        python_pid = _python_child_pid(parent.pid)
        log_path = perf_home / "uvx.log"
        _write_executable(perf_home / "bin" / "uvx", _fake_uvx_script(log_path))
        env = _base_env(perf_home, unused_port, parent.pid)
        result = _run_perf(env, extra_path=perf_home / "bin")
        assert result.returncode == 0, result.stderr
        recorded = log_path.read_text(encoding="utf-8")
        assert f"--pid {python_pid}" in recorded
        assert f"--pid {parent.pid}" not in recorded
    finally:
        _stop_process_group(parent)


def test_idle_mode_passes_idle_flag(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    proc, port = python_http_server
    log_path = perf_home / "uvx.log"
    _write_executable(perf_home / "bin" / "uvx", _fake_uvx_script(log_path))
    env = _base_env(perf_home, port, proc.pid)
    env["MODE"] = "idle"
    result = _run_perf(env, extra_path=perf_home / "bin")
    assert result.returncode == 0, result.stderr
    assert "--idle" in log_path.read_text(encoding="utf-8")
    assert list((perf_home / "out").glob("idle-*.svg"))


def test_ptrace_denial_prints_hint(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    proc, port = python_http_server
    _write_executable(
        perf_home / "bin" / "uvx",
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('Permission Denied: ptrace', file=sys.stderr)\n"
        "sys.exit(1)\n",
    )
    result = _run_perf(
        _base_env(perf_home, port, proc.pid), extra_path=perf_home / "bin"
    )
    assert result.returncode == 1
    assert "yama/ptrace_scope" in (result.stderr or "")
    assert "Do not rerun this script with sudo." in (result.stderr or "")


def test_mem_mode_requires_memray(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    if importlib.util.find_spec("memray") is not None:
        pytest.skip("memray is already installed in this environment")
    proc, port = python_http_server
    env = _base_env(perf_home, port, proc.pid)
    env["MODE"] = "mem"
    result = _run_perf(env)
    assert result.returncode == 2
    assert "uv sync --group perf --locked" in (result.stderr or "")


def test_mem_mode_attaches_and_writes_report(
    perf_home: Path, python_http_server: tuple[subprocess.Popen[str], int]
) -> None:
    proc, port = python_http_server
    log_path = perf_home / "uv.log"
    _write_executable(perf_home / "bin" / "uv", _fake_uv_script(log_path))
    env = _base_env(perf_home, port, proc.pid)
    env["MODE"] = "mem"
    result = _run_perf(env, extra_path=perf_home / "bin")
    assert result.returncode == 0, result.stderr
    assert list((perf_home / "out").glob("mem-*.bin"))
    assert list((perf_home / "out").glob("mem-*.html"))
    recorded = log_path.read_text(encoding="utf-8")
    assert "memray attach" in recorded
    assert "--no-sync" in recorded
    assert "sys.remote_exec" in recorded
    assert "memray flamegraph" in recorded
    assert f"{proc.pid}" in recorded
