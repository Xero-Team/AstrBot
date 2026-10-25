"""Linux sandbox bridge runner.

The host launches this script inside the sandbox network namespace. It starts
two unfiltered loopback relays to the host's Unix proxy sockets, signals
readiness, then forks a workload that installs the socket seccomp filter and
executes the requested command. The bridge process is never filtered so it can
keep opening Unix connections after the workload starts.
"""

from __future__ import annotations

import errno
import os
import select
import signal
import socket
import sys
import threading
import time
import warnings
from pathlib import Path

BRIDGE_HTTP_PORT = 31280
BRIDGE_SOCKS_PORT = 31080
_READY_TIMEOUT_SECONDS = 10.0
_RELAY_IDLE_SECONDS = 300.0
_SOCKET_POLL_SECONDS = 1.0
_MAX_RELAY_CONNECTIONS = 64


def _install_filter(mode: str) -> None:
    """Load the trusted sibling seccomp module in script and package contexts."""
    import importlib.util

    path = Path(__file__).resolve().with_name("seccomp.py")
    spec = importlib.util.spec_from_file_location("_astrbot_sandbox_seccomp", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("The sandbox seccomp module is unavailable.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install_socket_filter(mode)


def _parse_arguments(argv: list[str]) -> dict[str, object]:
    result: dict[str, object] = {
        "http_socket": "",
        "socks_socket": "",
        "http_port": 31280,
        "socks_port": 31080,
        "ready_file": "",
        "sockets": "deny",
        "filter_only": False,
        "workload": [],
    }
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument == "--filter-only":
            result["filter_only"] = True
            index += 1
            continue
        if argument == "--":
            result["workload"] = argv[index + 1 :]
            break
        if argument not in {
            "--http-socket",
            "--socks-socket",
            "--http-port",
            "--socks-port",
            "--ready-file",
            "--sockets",
        }:
            raise SystemExit(f"Unsupported bridge argument: {argument}")
        if index + 1 >= len(argv):
            raise SystemExit(f"Missing value for {argument}")
        value = argv[index + 1]
        key = argument.removeprefix("--").replace("-", "_")
        if key in {"http_port", "socks_port"}:
            result[key] = int(value)
        else:
            result[key] = value
        index += 2
    if not result["workload"]:
        raise SystemExit("The bridge requires a workload command.")
    return result


def _write_ready(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as handle:
        handle.write("ready\n")
        handle.flush()
        os.fsync(handle.fileno())


def _close_inherited_descriptors() -> None:
    """Close every non-stdio descriptor before the workload executes."""
    try:
        entries = os.listdir("/proc/self/fd")
    except OSError:
        return
    for entry in entries:
        try:
            descriptor = int(entry)
        except ValueError:
            continue
        if descriptor <= 2:
            continue
        try:
            os.close(descriptor)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise


def _close_quietly(*sockets: socket.socket | None) -> None:
    for current in sockets:
        if current is None:
            continue
        try:
            current.close()
        except OSError:
            # The socket may already be closed by the peer or the relay.
            pass


def _relay(
    left: socket.socket,
    right: socket.socket,
    stop: threading.Event,
) -> None:
    sockets = [left, right]
    last_activity = time.monotonic()
    try:
        while not stop.is_set():
            readable, _, errored = select.select(
                sockets, [], sockets, _SOCKET_POLL_SECONDS
            )
            if not readable and not errored:
                if time.monotonic() - last_activity >= _RELAY_IDLE_SECONDS:
                    return
                continue
            for current in errored:
                return
            for current in readable:
                other = right if current is left else left
                chunk = current.recv(65536)
                if not chunk:
                    try:
                        other.shutdown(socket.SHUT_WR)
                    except OSError:
                        # The opposite direction is already closed.
                        pass
                    return
                other.sendall(chunk)
                last_activity = time.monotonic()
    finally:
        _close_quietly(*sockets)


def _handle_connection(
    client: socket.socket,
    unix_path: str,
    stop: threading.Event,
    slots: threading.BoundedSemaphore,
) -> None:
    upstream: socket.socket | None = None
    try:
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        upstream.settimeout(_READY_TIMEOUT_SECONDS)
        upstream.connect(unix_path)
        upstream.settimeout(None)
        client.settimeout(None)
        _relay(client, upstream, stop)
    except OSError:
        _close_quietly(client, upstream)
    finally:
        slots.release()


def _bridge_loop(
    listener: socket.socket,
    unix_path: str,
    stop: threading.Event,
    failures: list[BaseException],
    slots: threading.BoundedSemaphore,
) -> None:
    listener.settimeout(_SOCKET_POLL_SECONDS)
    while not stop.is_set():
        try:
            client, _ = listener.accept()
        except TimeoutError:
            continue
        except OSError as exc:
            if stop.is_set():
                return
            failures.append(exc)
            return
        if not slots.acquire(blocking=False):
            _close_quietly(client)
            continue
        threading.Thread(
            target=_handle_connection,
            args=(client, unix_path, stop, slots),
            name="sandbox-bridge-relay",
            daemon=True,
        ).start()


def _wait_for_child(
    child: int,
    failures: list[BaseException],
    stop: threading.Event,
) -> int:
    killed_for_failure = False
    while True:
        try:
            waited_pid, status = os.waitpid(child, os.WNOHANG)
        except InterruptedError:
            continue
        except ChildProcessError:
            return 1
        if waited_pid == 0:
            pass
        elif os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            return 128 + os.WTERMSIG(status)
        if failures and not killed_for_failure:
            killed_for_failure = True
            stop.set()
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                # The child already exited before the failure kill.
                pass
        time.sleep(0.01)


def _apply_workload_environment(
    http_port: int,
    socks_port: int,
    token: str,
    ca_file: str,
) -> None:
    for key in list(os.environ):
        if key.lower() in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}:
            os.environ.pop(key, None)
    http_url = f"http://{token}@127.0.0.1:{http_port}"
    socks_url = f"socks5h://{token}@127.0.0.1:{socks_port}"
    os.environ["HTTP_PROXY"] = http_url
    os.environ["HTTPS_PROXY"] = http_url
    os.environ["ALL_PROXY"] = socks_url
    os.environ["http_proxy"] = http_url
    os.environ["https_proxy"] = http_url
    os.environ["all_proxy"] = socks_url
    os.environ["NO_PROXY"] = ""
    os.environ["no_proxy"] = ""
    if ca_file and Path(ca_file).is_file():
        os.environ["SSL_CERT_FILE"] = ca_file
        os.environ["REQUESTS_CA_BUNDLE"] = ca_file
        os.environ["CURL_CA_BUNDLE"] = ca_file


def main(argv: list[str] | None = None) -> int:
    """Run the bridge and workload, returning the workload exit status."""
    arguments = _parse_arguments(argv or sys.argv)
    http_socket = str(arguments["http_socket"])
    socks_socket = str(arguments["socks_socket"])
    http_port_value = arguments["http_port"]
    socks_port_value = arguments["socks_port"]
    if not isinstance(http_port_value, int) or not isinstance(socks_port_value, int):
        raise SystemExit("The sandbox bridge received invalid proxy ports.")
    http_port = http_port_value
    socks_port = socks_port_value
    ready_file = Path(str(arguments["ready_file"]))
    socket_mode = str(arguments["sockets"])
    workload_value = arguments["workload"]
    if not isinstance(workload_value, list):
        raise SystemExit("The sandbox bridge workload is invalid.")
    workload = [str(item) for item in workload_value]

    if bool(arguments["filter_only"]):
        try:
            _close_inherited_descriptors()
            if socket_mode == "deny":
                _install_filter("deny")
            os.execvpe(  # noqa: S606  # workload argv is built by the host sandbox launcher
                workload[0], workload, os.environ
            )
        except Exception as exc:  # child must report and exit
            try:
                sys.stderr.write(f"sandbox workload failed to start: {exc}\n")
                sys.stderr.flush()
            finally:
                os._exit(127)
    token = os.environ.pop("ASTRBOT_SANDBOX_PROXY_TOKEN", "")
    ca_file = os.environ.pop("ASTRBOT_SANDBOX_CA_FILE", "")
    if not token:
        raise SystemExit("The sandbox bridge is missing its proxy token.")

    listeners: list[socket.socket] = []
    try:
        for address, port in (
            ("127.0.0.1", http_port),
            ("127.0.0.1", socks_port),
        ):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((address, port))
            listener.listen(64)
            listeners.append(listener)
    except OSError as exc:
        raise SystemExit(f"The sandbox bridge could not bind its proxy ports: {exc}")

    stop = threading.Event()
    failures: list[BaseException] = []
    slots = threading.BoundedSemaphore(_MAX_RELAY_CONNECTIONS)
    threads = [
        threading.Thread(
            target=_bridge_loop,
            args=(listeners[0], http_socket, stop, failures, slots),
            name="sandbox-bridge-http",
            daemon=True,
        ),
        threading.Thread(
            target=_bridge_loop,
            args=(listeners[1], socks_socket, stop, failures, slots),
            name="sandbox-bridge-socks",
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    _write_ready(ready_file)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        child = os.fork()
    if child == 0:
        try:
            stop.set()
            for listener in listeners:
                listener.close()
            _close_inherited_descriptors()
            if socket_mode == "deny":
                _install_filter("deny")
            _apply_workload_environment(
                http_port,
                socks_port,
                token,
                ca_file,
            )
            os.execvpe(  # noqa: S606  # workload argv is built by the host sandbox launcher
                workload[0], workload, os.environ
            )
        except Exception as exc:  # child must report and exit
            try:
                sys.stderr.write(f"sandbox workload failed to start: {exc}\n")
                sys.stderr.flush()
            finally:
                os._exit(127)

    received_signal = 0

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal received_signal
        received_signal = signum
        stop.set()
        try:
            os.kill(child, signum)
        except ProcessLookupError:
            # The child already exited before the signal was forwarded.
            pass

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, request_stop)

    exit_code = _wait_for_child(child, failures, stop)
    stop.set()
    for listener in listeners:
        try:
            listener.close()
        except OSError:
            # Listener sockets may already be closed by the child branch.
            pass
    if received_signal and exit_code == 0:
        exit_code = 128 + received_signal
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
