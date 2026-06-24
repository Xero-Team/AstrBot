import shutil
import tempfile
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import TypedDict
from zipfile import ZipFile

import click
import httpx
import yaml

from .version_comparator import VersionComparator


class PluginStatus(StrEnum):
    INSTALLED = "installed"
    NEED_UPDATE = "needs-update"
    NOT_INSTALLED = "not-installed"
    NOT_PUBLISHED = "unpublished"


class PluginRecord(TypedDict):
    name: str
    desc: str
    version: str
    author: str
    repo: str
    status: PluginStatus
    local_path: str | None


def _resolve_download_url(url: str, proxy: str | None = None) -> str:
    """Resolve the preferred archive URL for a GitHub repository.

    Args:
        url: Repository URL or direct archive URL.
        proxy: Optional proxy prefix or HTTP proxy address.

    Returns:
        The archive URL to download.
    """
    repo_namespace = url.split("/")[-2:]
    if len(repo_namespace) != 2:
        return url

    author, repo = repo_namespace
    release_url = f"https://api.github.com/repos/{author}/{repo}/releases"
    try:
        with httpx.Client(
            proxy=proxy if proxy else None,
            follow_redirects=True,
        ) as client:
            resp = client.get(release_url)
            resp.raise_for_status()
            releases = resp.json()
    except Exception as e:
        click.echo(f"Failed to get release info: {e}. Using provided URL directly")
        return url

    if releases:
        return str(releases[0]["zipball_url"])

    click.echo(f"Downloading {author}/{repo} from default branch")
    return f"https://github.com/{author}/{repo}/archive/refs/heads/master.zip"


def _download_plugin_archive(
    download_url: str,
    proxy: str | None = None,
) -> BytesIO:
    """Download a plugin archive and return it as an in-memory ZIP stream.

    Args:
        download_url: Archive URL to fetch.
        proxy: Optional proxy prefix or HTTP proxy address.

    Returns:
        Downloaded archive bytes wrapped in ``BytesIO``.
    """
    if proxy:
        download_url = f"{proxy}/{download_url}"

    with httpx.Client(
        proxy=proxy if proxy else None,
        follow_redirects=True,
    ) as client:
        resp = client.get(download_url)
        if resp.status_code == 404 and "archive/refs/heads/master.zip" in download_url:
            alt_url = download_url.replace("master.zip", "main.zip")
            click.echo("Branch 'master' not found, trying 'main' branch")
            resp = client.get(alt_url)
        resp.raise_for_status()
        return BytesIO(resp.content)


def get_git_repo(url: str, target_path: Path, proxy: str | None = None) -> None:
    """Download code from a Git repository and extract to the specified path.

    Args:
        url: Repository URL or direct archive URL.
        target_path: Local target directory for extracted content.
        proxy: Optional proxy prefix or HTTP proxy address.
    """
    temp_dir = Path(tempfile.mkdtemp())
    try:
        zip_content = _download_plugin_archive(
            _resolve_download_url(url, proxy),
            proxy,
        )
        with ZipFile(zip_content) as z:
            z.extractall(temp_dir)
            namelist = z.namelist()
            root_dir = Path(namelist[0]).parts[0] if namelist else ""
            if target_path.exists():
                shutil.rmtree(target_path)
            shutil.move(temp_dir / root_dir, target_path)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def load_yaml_metadata(plugin_dir: Path) -> dict:
    """Load plugin metadata from metadata.yaml file

    Args:
        plugin_dir: Plugin directory path

    Returns:
        dict: Dictionary containing metadata, or empty dict if loading fails

    """
    yaml_path = plugin_dir / "metadata.yaml"
    if yaml_path.exists():
        try:
            return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            click.echo(f"Failed to read {yaml_path}: {e}", err=True)
    return {}


def _build_plugin_record(
    *,
    name: str,
    desc: str,
    version: str,
    author: str,
    repo: str,
    status: PluginStatus,
    local_path: str | None,
) -> PluginRecord:
    return {
        "name": name,
        "desc": desc,
        "version": version,
        "author": author,
        "repo": repo,
        "status": status,
        "local_path": local_path,
    }


def _load_local_plugin(plugin_dir: Path) -> PluginRecord | None:
    metadata = load_yaml_metadata(plugin_dir)
    required_keys = {"name", "desc", "version", "author", "repo"}
    if not metadata or not required_keys.issubset(metadata):
        return None

    return _build_plugin_record(
        name=str(metadata.get("name", "")),
        desc=str(metadata.get("desc", "")),
        version=str(metadata.get("version", "")),
        author=str(metadata.get("author", "")),
        repo=str(metadata.get("repo", "")),
        status=PluginStatus.INSTALLED,
        local_path=str(plugin_dir),
    )


def _fetch_online_plugins() -> dict[str, PluginRecord]:
    online_plugins: dict[str, PluginRecord] = {}
    try:
        with httpx.Client() as client:
            resp = client.get("https://api.soulter.top/astrbot/plugins")
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        click.echo(f"Failed to get online plugin list: {e}", err=True)
        return online_plugins

    for plugin_id, plugin_info in data.items():
        online_plugins[str(plugin_id)] = _build_plugin_record(
            name=str(plugin_id),
            desc=str(plugin_info.get("desc", "")),
            version=str(plugin_info.get("version", "")),
            author=str(plugin_info.get("author", "")),
            repo=str(plugin_info.get("repo", "")),
            status=PluginStatus.NOT_INSTALLED,
            local_path=None,
        )
    return online_plugins


def _get_plugin_target_paths(
    plugin: PluginRecord,
    plugins_dir: Path,
    *,
    is_update: bool,
) -> tuple[str, str, Path, Path | None]:
    plugin_name = plugin["name"]
    repo_url = plugin["repo"]
    local_path = plugin.get("local_path")
    target_path = (
        Path(local_path) if is_update and local_path else plugins_dir / plugin_name
    )
    backup_path = (
        target_path.with_name(f"{target_path.name}_backup") if is_update else None
    )
    return plugin_name, repo_url, target_path, backup_path


def _prepare_plugin_backup(target_path: Path, backup_path: Path | None) -> None:
    if backup_path is None:
        return
    if backup_path.exists():
        shutil.rmtree(backup_path)
    shutil.copytree(target_path, backup_path)


def _cleanup_plugin_backup(backup_path: Path | None) -> None:
    if backup_path is not None and backup_path.exists():
        shutil.rmtree(backup_path)


def _restore_plugin_backup(target_path: Path, backup_path: Path | None) -> None:
    if target_path.exists():
        shutil.rmtree(target_path, ignore_errors=True)
    if backup_path is not None and backup_path.exists():
        shutil.move(backup_path, target_path)


def build_plug_list(plugins_dir: Path) -> list[PluginRecord]:
    """Build plugin list containing local and online plugin information

    Args:
        plugins_dir: Plugin directory path

    Returns:
        List of dicts containing plugin information.
    """
    result: list[PluginRecord] = []
    if plugins_dir.is_dir():
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            plugin_record = _load_local_plugin(plugin_dir)
            if plugin_record is not None:
                result.append(plugin_record)

    online_plugins_dict = _fetch_online_plugins()

    for local_plugin in result:
        plugin_name = str(local_plugin["name"])
        online_plugin = online_plugins_dict.pop(plugin_name, None)
        if online_plugin is None:
            local_plugin["status"] = PluginStatus.NOT_PUBLISHED
            continue

        if (
            VersionComparator.compare_version(
                local_plugin["version"],
                online_plugin["version"],
            )
            < 0
        ):
            local_plugin["status"] = PluginStatus.NEED_UPDATE

    result.extend(online_plugins_dict.values())
    return result


def manage_plugin(
    plugin: PluginRecord,
    plugins_dir: Path,
    is_update: bool = False,
    proxy: str | None = None,
) -> None:
    """Install or update a plugin.

    Args:
        plugin: Plugin info dict.
        plugins_dir: Plugins directory.
        is_update: Whether this is an update operation.
        proxy: Proxy server address.
    """
    plugin_name, repo_url, target_path, backup_path = _get_plugin_target_paths(
        plugin,
        plugins_dir,
        is_update=is_update,
    )

    if is_update and not target_path.exists():
        raise click.ClickException(
            f"Plugin {plugin_name} is not installed and cannot be updated"
        )

    _prepare_plugin_backup(target_path, backup_path)

    try:
        click.echo(
            f"{'Updating' if is_update else 'Downloading'} plugin {plugin_name} from {repo_url}...",
        )
        get_git_repo(repo_url, target_path, proxy)

        _cleanup_plugin_backup(backup_path)
        click.echo(
            f"Plugin {plugin_name} {'updated' if is_update else 'installed'} successfully"
        )
    except Exception as e:
        _restore_plugin_backup(target_path, backup_path)
        raise click.ClickException(
            f"Error {'updating' if is_update else 'installing'} plugin {plugin_name}: {e}",
        )
