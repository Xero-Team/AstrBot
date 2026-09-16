from __future__ import annotations

import platform
import shutil
import sys
import tempfile
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from .base import (
    ProcessSandbox,
    SandboxLimits,
    SandboxProcess,
    SandboxRunResult,
    SandboxSpec,
    SandboxTimeoutError,
)


def create_process_sandbox() -> ProcessSandbox:
    """Select the restricted-process launcher for the current system.

    Returns:
        Bubblewrap on Linux or Seatbelt on macOS.

    Raises:
        RuntimeError: If the current system has no Local sandbox implementation
            or the required launcher is missing.
    """
    if sys.platform.startswith("linux"):
        if not shutil.which("bwrap"):
            raise RuntimeError(
                "bubblewrap (`bwrap`) is required for restricted Local execution."
            )
        from .bubblewrap import BubblewrapProcessSandbox

        return BubblewrapProcessSandbox()
    if sys.platform == "darwin":
        if shutil.which("sandbox-exec", path="/usr/bin") != "/usr/bin/sandbox-exec":
            raise RuntimeError(
                "Seatbelt (`/usr/bin/sandbox-exec`) is required for restricted "
                "Local execution."
            )
        from .seatbelt import SeatbeltProcessSandbox

        return SeatbeltProcessSandbox()
    raise RuntimeError("No Local process sandbox backend is available.")


def detect_local_runtime_info(*, probe: bool = False) -> dict:
    """Probe OS, architecture, and Local sandbox availability once.

    Args:
        probe: When True, launch a 5s sandbox no-op if the backend is present.
            Config saves should leave this false; the Dashboard version snapshot
            can afford the extra process.

    Returns:
        Runtime snapshot consumed by the Dashboard version API and Local
        permission validation. Restart AstrBot after installing sandbox
        dependencies to refresh it.
    """
    system = platform.system().lower()
    sandbox: dict = {"backend": None, "status": "unsupported"}
    if system == "linux":
        sandbox = {
            "backend": "bubblewrap",
            "status": "detected" if shutil.which("bwrap") else "missing",
        }
    elif system == "darwin":
        sandbox = {
            "backend": "seatbelt",
            "status": (
                "detected"
                if shutil.which("sandbox-exec", path="/usr/bin")
                == "/usr/bin/sandbox-exec"
                else "missing"
            ),
        }
    if probe and sandbox["status"] == "detected":
        try:
            temp_root = Path(get_astrbot_temp_path())
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="sandbox-probe-", dir=temp_root
            ) as workspace:
                result = create_process_sandbox().run(
                    ["/bin/sh", "-c", ":"],
                    SandboxSpec(workspace=Path(workspace)),
                    timeout=5,
                    output_limit=1024,
                )
            if result.returncode != 0:
                raise RuntimeError(
                    result.stderr.decode("utf-8", errors="replace").strip()
                    or f"Sandbox probe exited with code {result.returncode}."
                )
        except (OSError, RuntimeError) as exc:
            sandbox.update(
                status="unavailable", error=str(exc)[:1024] or type(exc).__name__
            )
    return {
        "os": system,
        "arch": platform.machine(),
        "sandbox": sandbox,
    }


__all__ = (
    "ProcessSandbox",
    "SandboxLimits",
    "SandboxProcess",
    "SandboxRunResult",
    "SandboxSpec",
    "SandboxTimeoutError",
    "create_process_sandbox",
    "detect_local_runtime_info",
)
