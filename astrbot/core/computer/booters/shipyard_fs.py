from __future__ import annotations

from typing import Any

from shipyard import FileSystemComponent as ShipyardFileSystemComponent

from ..olayer import ShellComponent
from .shipyard_search_file_util import search_files_via_shell


class ShipyardFileSystemWrapper:
    def __init__(
        self, _shipyard_fs: ShipyardFileSystemComponent, _shipyard_shell: ShellComponent
    ):
        self._fs = _shipyard_fs
        self._shell = _shipyard_shell

    async def create_file(
        self, path: str, content: str = "", mode: int = 420
    ) -> dict[str, Any]:
        return await self._fs.create_file(path=path, content=content, mode=mode)

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self._fs.read_file(
            path=path, encoding=encoding, offset=offset, limit=limit
        )

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        return await self._fs.write_file(
            path=path, content=content, mode=mode, encoding=encoding
        )

    async def list_dir(
        self, path: str = ".", show_hidden: bool = False
    ) -> dict[str, Any]:
        return await self._fs.list_dir(path=path, show_hidden=show_hidden)

    async def delete_file(self, path: str) -> dict[str, Any]:
        return await self._fs.delete_file(path=path)

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
    ) -> dict[str, Any]:
        return await search_files_via_shell(
            self._shell,
            pattern=pattern,
            path=path,
            glob=glob,
            after_context=after_context,
            before_context=before_context,
        )

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        return await self._fs.edit_file(
            path=path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
            encoding=encoding,
        )
