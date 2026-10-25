import sys

from astrbot import logger

from .booters.base import ComputerBooter
from .booters.local import LocalBooter, resolve_windows_shell


class ComputerRuntime:
    """Runtime-owned local computer capability."""

    def __init__(self) -> None:
        self._local_booter: ComputerBooter | None = None
        self._terminated = False

    def _ensure_active(self) -> None:
        if self._terminated:
            raise RuntimeError("Computer runtime has been terminated.")

    def get_local_booter(self) -> ComputerBooter:
        """Return this runtime's lazily constructed local booter."""
        self._ensure_active()
        if self._local_booter is None:
            self._local_booter = LocalBooter()
            if sys.platform == "win32":
                logger.info(
                    "[Computer] Windows local runtime shell: %s",
                    resolve_windows_shell(),
                )
        return self._local_booter

    async def terminate(self) -> None:
        """Terminate the local booter owned by this runtime."""
        if self._terminated:
            return
        self._terminated = True

        local_booter, self._local_booter = self._local_booter, None
        if local_booter is not None:
            try:
                await local_booter.shutdown()
            except Exception as exc:
                logger.warning("Failed to terminate local computer runtime: %s", exc)
