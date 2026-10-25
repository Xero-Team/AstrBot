import sys

from astrbot import logger

from .booters.base import ComputerBooter
from .booters.local import LocalBooter, resolve_windows_shell
from .process_sandbox.proxy import LocalProxyServer


class ComputerRuntime:
    """Runtime-owned local computer capability."""

    def __init__(self) -> None:
        self._local_booter: ComputerBooter | None = None
        self._local_proxy: LocalProxyServer | None = None
        self._terminated = False

    def _ensure_active(self) -> None:
        if self._terminated:
            raise RuntimeError("Computer runtime has been terminated.")

    def get_local_booter(self) -> ComputerBooter:
        """Return this runtime's lazily constructed local booter."""
        self._ensure_active()
        if self._local_booter is None:
            self._local_booter = LocalBooter(proxy_provider=self.get_local_proxy)
            if sys.platform == "win32":
                logger.info(
                    "[Computer] Windows local runtime shell: %s",
                    resolve_windows_shell(),
                )
        return self._local_booter

    def get_local_proxy(self) -> LocalProxyServer:
        """Return the runtime-owned proxy, starting it on first sandboxed use."""
        self._ensure_active()
        if self._local_proxy is None or self._local_proxy.state in {"stopped"}:
            proxy = LocalProxyServer()
            proxy.start()
            self._local_proxy = proxy
        return self._local_proxy

    async def terminate(self) -> None:
        """Terminate the local booter and proxy owned by this runtime."""
        if self._terminated:
            return
        self._terminated = True

        local_booter, self._local_booter = self._local_booter, None
        if local_booter is not None:
            try:
                await local_booter.shutdown()
            except Exception as exc:
                logger.warning("Failed to terminate local computer runtime: %s", exc)
        proxy, self._local_proxy = self._local_proxy, None
        if proxy is not None:
            try:
                await proxy.stop()
            except Exception as exc:
                logger.warning("Failed to stop local computer proxy: %s", exc)
