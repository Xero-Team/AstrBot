"""Bridge runner argument parsing and filter-only behavior."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from astrbot.core.computer.process_sandbox import bridge
from astrbot.core.computer.process_sandbox.seccomp import (
    build_socket_filter,
    current_audit_arch,
)


def test_bridge_ports_and_argument_contract() -> None:
    assert bridge.BRIDGE_HTTP_PORT == 31280
    assert bridge.BRIDGE_SOCKS_PORT == 31080
    parsed = bridge._parse_arguments(  # noqa: SLF001
        [
            "bridge.py",
            "--http-socket",
            "/tmp/http.sock",
            "--socks-socket",
            "/tmp/socks.sock",
            "--http-port",
            "31280",
            "--socks-port",
            "31080",
            "--ready-file",
            "/tmp/ready",
            "--sockets",
            "deny",
            "--",
            "/bin/echo",
            "hello",
        ]
    )
    assert parsed["http_socket"] == "/tmp/http.sock"
    assert parsed["workload"] == ["/bin/echo", "hello"]
    assert parsed["sockets"] == "deny"


def test_bridge_rejects_missing_workload() -> None:
    with pytest.raises(SystemExit):
        bridge._parse_arguments(["bridge.py", "--http-port", "1"])  # noqa: SLF001


def test_filter_only_runner_source_has_no_package_imports() -> None:
    source = Path(bridge.__file__).read_text(encoding="utf-8")
    assert 'with_name("seccomp.py")' in source
    assert "from seccomp import" not in source
    assert "astrbot." not in source
    assert build_socket_filter(architecture=current_audit_arch()).filters


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Filter-only bridge execution requires Linux.",
)
def test_filter_only_bridge_executes_workload_with_denied_unix_sockets() -> None:
    code = (
        "import socket\n"
        "try:\n"
        "    socket.socket(socket.AF_UNIX)\n"
        "except OSError as exc:\n"
        "    assert exc.errno == 13\n"
        "else:\n"
        "    raise AssertionError('Unix socket allowed')\n"
        "print('bridge-filter-ok')\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(Path(bridge.__file__)),
            "--filter-only",
            "--sockets",
            "deny",
            "--",
            sys.executable,
            "-c",
            code,
        ],
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2],
        timeout=30,
        env={"PATH": os.defpath},
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"bridge-filter-ok" in result.stdout


@pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Descriptor inheritance checks require the Linux bridge runner.",
)
def test_filter_only_bridge_closes_inherited_descriptors() -> None:
    read_fd, write_fd = os.pipe()
    try:
        code = (
            "import os\n"
            f"try:\n    os.fstat({read_fd})\n"
            "except OSError as exc:\n    assert exc.errno == 9\n"
            "else:\n    raise SystemExit('inherited descriptor remained open')\n"
            "print('descriptor-closed')\n"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-S",
                str(Path(bridge.__file__)),
                "--filter-only",
                "--sockets",
                "deny",
                "--",
                sys.executable,
                "-c",
                code,
            ],
            capture_output=True,
            cwd=Path(__file__).resolve().parents[2],
            timeout=30,
            env={"PATH": os.defpath},
            pass_fds=(read_fd,),
        )
        assert result.returncode == 0, result.stderr.decode()
        assert b"descriptor-closed" in result.stdout
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="The bridge relay uses Unix sockets.",
)
def test_bridge_serves_concurrent_connections(tmp_path: Path) -> None:
    unix_path = tmp_path / "echo.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(unix_path))
    server.listen(8)
    server.settimeout(0.2)
    server_stop = threading.Event()

    def echo(connection: socket.socket) -> None:
        try:
            while data := connection.recv(4096):
                connection.sendall(b"echo:" + data)
        except OSError:
            return
        finally:
            connection.close()

    def serve() -> None:
        while not server_stop.is_set():
            try:
                connection, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(target=echo, args=(connection,), daemon=True).start()

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = listener.getsockname()[1]
    stop = threading.Event()
    failures: list[BaseException] = []
    slots = threading.BoundedSemaphore(4)
    loop = threading.Thread(
        target=bridge._bridge_loop,  # noqa: SLF001
        args=(listener, str(unix_path), stop, failures, slots),
        daemon=True,
    )
    loop.start()

    first = socket.create_connection(("127.0.0.1", port), timeout=2)
    try:
        second = socket.create_connection(("127.0.0.1", port), timeout=2)
        try:
            second.sendall(b"ping")
            assert second.recv(64) == b"echo:ping"
        finally:
            second.close()
    finally:
        first.close()
        stop.set()
        listener.close()
        server_stop.set()
        server.close()
        loop.join(3)
        server_thread.join(3)

    assert failures == []
    assert not loop.is_alive()
    assert not server_thread.is_alive()
