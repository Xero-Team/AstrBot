from ..olayer import FileSystemComponent, PythonComponent, ShellComponent


class ComputerBooter:
    @property
    def fs(self) -> FileSystemComponent: ...

    @property
    def python(self) -> PythonComponent: ...

    @property
    def shell(self) -> ShellComponent: ...

    async def boot(self, session_id: str) -> None: ...

    async def shutdown(self, **kwargs) -> None:
        """Shut down the computer sandbox."""
        ...

    async def available(self) -> bool:
        """Check if the computer is available."""
        ...
