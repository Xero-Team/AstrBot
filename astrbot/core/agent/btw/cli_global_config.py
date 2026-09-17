"""Provider presets the operator switches a coding CLI between.

This is the configuration half of what a provider switcher does: the operator
keeps a list of providers per CLI, and making one current writes it into that
CLI's own global configuration.  There is deliberately no routing, proxying, or
format conversion here -- a run still layers its own config over whatever the
CLI reads, so nothing about a delegated run changes.

The list is AstrBot's own (``btw.cli_providers``) rather than a coding agent's
``providers``: an agent's presets exist to configure *a delegated run*, and are
scoped to that agent, whereas this list is what the CLI uses for everything the
operator does by hand.

Two files are involved per CLI and neither is ours:

* Claude Code keeps everything in ``~/.claude/settings.json``, and merges the
  ``env`` block over the process environment.  It is JSON, so it is parsed,
  merged key by key, and written back with every other key preserved.
* Codex keeps ``~/.codex/config.toml`` and ``~/.codex/auth.json``.  The standard
  library reads TOML but cannot write it, and rewriting a file we cannot parse
  faithfully would drop the user's comments, so AstrBot's keys are written as a
  comment-delimited section instead.  TOML requires top-level keys to precede
  every table, so the section goes at the top of the file and the rest is left
  byte for byte as it was.

Everything is backed up once before the first write, written atomically, and
restricted to the owner when it holds a credential.
"""

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from astrbot import logger

CODING_GLOBAL_AGENT_TYPES = ("claude_code", "codex")

# What AstrBot writes into a file it does not own.
CLAUDE_SETTINGS_FILE = "settings.json"
CODEX_CONFIG_FILE = "config.toml"
CODEX_AUTH_FILE = "auth.json"
CODEX_PROVIDER_ID = "astrbot_btw"
CODEX_MANAGED_BEGIN = "# >>> astrbot btw (managed; do not edit between these lines)"
CODEX_MANAGED_END = "# <<< astrbot btw"
# Every credential AstrBot stores in ``auth.json`` is named with this prefix.
_CODEX_KEY_PREFIX = "ASTRBOT_BTW_CODEX_KEY_"

# A one-time copy of the file as it was before AstrBot first wrote to it.
BACKUP_SUFFIX = ".astrbot-backup"
# A file holding a credential is readable by its owner and nobody else.
PRIVATE_FILE_MODE = 0o600


@dataclass(frozen=True, slots=True)
class ManagedFile:
    """One file AstrBot writes into, and what it currently holds."""

    path: Path
    exists: bool
    managed: bool
    # What AstrBot last wrote, as far as it can be read back.  A credential is
    # reported as present, never as its value.
    base_url: str
    model: str
    has_credential: bool
    backed_up: bool


def claude_home() -> Path:
    """Return the Claude Code configuration directory."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def codex_home() -> Path:
    """Return the Codex configuration directory."""
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def target_path(cli: str) -> Path:
    """Return the file a provider for ``cli`` is written into."""
    if cli == "claude_code":
        return claude_home() / CLAUDE_SETTINGS_FILE
    if cli == "codex":
        return codex_home() / CODEX_CONFIG_FILE
    raise ValueError(f"Unknown coding agent type: {cli!r}")


def provider_slug(provider_id: object) -> str:
    """Return the filesystem-safe form of a provider id."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(provider_id or "provider")).strip("-.")
    return safe[:64] or "provider"


def credential_env_name(provider_id: object) -> str:
    """Return the variable a Codex provider's section reads its key from."""
    return f"{_CODEX_KEY_PREFIX}{provider_slug(provider_id).upper().replace('-', '_')}"


# ── the provider list ────────────────────────────────────────────────────────


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def normalize_cli_providers(raw: object) -> list[dict]:
    """Return the usable provider entries of a profile, in order.

    A malformed entry is dropped rather than raised: the list comes from a
    profile, and one bad entry must not stop the others from being usable.
    """
    providers: list[dict] = []
    seen: set[str] = set()
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, Mapping):
            continue
        provider_id = _text(entry.get("id")).strip()
        if not provider_id or provider_id in seen:
            continue
        seen.add(provider_id)
        providers.append(
            {
                "id": provider_id,
                "name": _text(entry.get("name"), provider_id).strip() or provider_id,
                "cli": _text(entry.get("cli")).strip(),
                "base_url": _text(entry.get("base_url")).strip(),
                "api_key": _text(entry.get("api_key")).strip(),
                "model": _text(entry.get("model")).strip(),
                "note": _text(entry.get("note")).strip(),
            }
        )
    return providers


def providers_for_cli(raw: object, cli: str) -> list[dict]:
    """Return the entries that apply to one CLI, and the ones for both.

    An entry with no ``cli`` applies to every CLI AstrBot knows how to write,
    which is what an operator means when they do not pick one.
    """
    return [
        provider
        for provider in normalize_cli_providers(raw)
        if not provider["cli"] or provider["cli"] == cli
    ]


def select_provider(raw: object, provider_id: str) -> dict | None:
    """Return the named provider, or ``None`` when the list has no such id."""
    wanted = provider_id.strip()
    if not wanted:
        return None
    for provider in normalize_cli_providers(raw):
        if provider["id"] == wanted:
            return provider
    return None


# ── reading and writing the CLI's own files ──────────────────────────────────


def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + BACKUP_SUFFIX)


def _read_json(path: Path) -> dict:
    """Return a JSON object from ``path``, or an empty one.

    A file that cannot be parsed is treated as absent rather than replaced: the
    operator's own configuration is not this module's to discard.
    """
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError, ValueError:
        logger.warning("%s is not valid JSON; leaving it alone.", path)
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write(path: Path, text: str, *, private: bool) -> None:
    """Replace ``path`` so a reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".astrbot-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            os.chmod(temporary, PRIVATE_FILE_MODE)
        os.replace(temporary, path)
        temporary = None
        _fsync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    """Flush a directory entry, where the platform lets us open one.

    Best effort by design: neither step is what makes the write correct, and a
    platform that refuses either one still has the rename, which is the part
    that matters.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        # Windows cannot open a directory this way.
        return
    try:
        os.fsync(descriptor)
    except OSError:
        # A filesystem that does not support it; the rename already landed.
        pass
    finally:
        os.close(descriptor)


def _back_up_once(path: Path) -> Path | None:
    """Copy the file aside the first time AstrBot writes to it."""
    if not path.is_file():
        return None
    backup = _backup_path(path)
    if backup.exists():
        return backup
    _atomic_write(backup, path.read_text(encoding="utf-8"), private=False)
    return backup


def _managed_block(base_url: str, model: str, env_key: str) -> str:
    """Return the Codex section AstrBot owns."""
    lines = [CODEX_MANAGED_BEGIN]
    lines.append(f"model_provider = {json.dumps(CODEX_PROVIDER_ID)}")
    if model:
        lines.append(f"model = {json.dumps(model)}")
    lines.append("")
    lines.append(f"[model_providers.{CODEX_PROVIDER_ID}]")
    lines.append(f"name = {json.dumps('AstrBot')}")
    lines.append(f"base_url = {json.dumps(base_url)}")
    if env_key:
        lines.append(f'env_key = "{env_key}"')
    lines.append(f"wire_api = {json.dumps('responses')}")
    lines.append(CODEX_MANAGED_END)
    return "\n".join(lines)


def _strip_managed_block(text: str) -> str:
    """Return ``text`` without AstrBot's section, keeping everything else."""
    start = text.find(CODEX_MANAGED_BEGIN)
    if start == -1:
        return text
    end = text.find(CODEX_MANAGED_END, start)
    if end == -1:
        # No closing marker: the file was edited by hand or truncated.  Leave it
        # alone rather than guess where the section was meant to end.
        return text
    end += len(CODEX_MANAGED_END)
    while end < len(text) and text[end] == "\n":
        end += 1
    return text[:start] + text[end:]


def read_state(cli: str) -> ManagedFile:
    """Report what the CLI's global config currently holds.

    Never returns a credential, only whether one is present.
    """
    path = target_path(cli)
    if cli == "claude_code":
        payload = _read_json(path)
        env = payload.get("env")
        env = env if isinstance(env, Mapping) else {}
        return ManagedFile(
            path=path,
            exists=path.is_file(),
            # Claude Code merges `env`, so AstrBot has no section of its own to
            # point at: it manages exactly the keys it writes.
            managed=any(
                key in env
                for key in (
                    "ANTHROPIC_BASE_URL",
                    "ANTHROPIC_MODEL",
                    "ANTHROPIC_AUTH_TOKEN",
                )
            ),
            base_url=str(env.get("ANTHROPIC_BASE_URL", "") or ""),
            model=str(env.get("ANTHROPIC_MODEL", "") or ""),
            has_credential=bool(env.get("ANTHROPIC_AUTH_TOKEN")),
            backed_up=_backup_path(path).is_file(),
        )

    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    base_url = ""
    model = ""
    env_key = ""
    start = text.find(CODEX_MANAGED_BEGIN)
    end = text.find(CODEX_MANAGED_END, start) if start != -1 else -1
    if start != -1 and end != -1:
        for line in text[start:end].splitlines():
            key, _, value = line.partition("=")
            value = value.strip().strip('"')
            if key.strip() == "base_url":
                base_url = value
            elif key.strip() == "model":
                model = value
            elif key.strip() == "env_key":
                env_key = value
    auth = _read_json(codex_home() / CODEX_AUTH_FILE)
    return ManagedFile(
        path=path,
        exists=path.is_file(),
        managed=start != -1 and end != -1,
        base_url=base_url,
        model=model,
        has_credential=bool(auth.get(env_key)) if env_key else False,
        backed_up=_backup_path(path).is_file(),
    )


def apply_provider(cli: str, provider: Mapping) -> ManagedFile:
    """Make one provider the CLI's default on this host.

    Args:
        cli: ``claude_code`` or ``codex``.
        provider: A normalized provider entry.

    Returns:
        The state the target file is in after the write.
    """
    if cli not in CODING_GLOBAL_AGENT_TYPES:
        raise ValueError(f"Unknown coding agent type: {cli!r}")
    provider_id = _text(provider.get("id")).strip()
    base_url = _text(provider.get("base_url")).strip()
    model = _text(provider.get("model")).strip()
    api_key = _text(provider.get("api_key")).strip()
    if not provider_id:
        raise ValueError("A provider needs an id before it can be applied.")
    if not base_url and not api_key:
        raise ValueError(
            "A provider needs an endpoint or a key before it can be applied."
        )

    path = target_path(cli)
    _back_up_once(path)

    if cli == "claude_code":
        payload = _read_json(path)
        env = payload.get("env")
        env = dict(env) if isinstance(env, Mapping) else {}
        env["ANTHROPIC_BASE_URL"] = base_url
        if model:
            env["ANTHROPIC_MODEL"] = model
        else:
            env.pop("ANTHROPIC_MODEL", None)
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
        else:
            env.pop("ANTHROPIC_AUTH_TOKEN", None)
        payload["env"] = env
        _atomic_write(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            private=bool(api_key),
        )
        return read_state(cli)

    env_key = credential_env_name(provider_id)
    existing = (
        path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    )
    block = _managed_block(base_url, model, env_key if api_key else "")
    rest = _strip_managed_block(existing)
    _atomic_write(path, f"{block}\n" + (f"\n{rest}" if rest else ""), private=False)

    _apply_codex_credential(env_key, api_key)
    return read_state(cli)


def _apply_codex_credential(env_key: str, api_key: str) -> None:
    """Put one provider's key in ``auth.json``, or take it out.

    Only this provider's own variable is touched: switching to a provider that
    has no key must not delete the key a different provider stored.
    """
    auth_path = codex_home() / CODEX_AUTH_FILE
    if not api_key and not auth_path.is_file():
        return
    _back_up_once(auth_path)
    auth = _read_json(auth_path)
    if api_key:
        auth[env_key] = api_key
    else:
        auth.pop(env_key, None)
    if auth or auth_path.is_file():
        _atomic_write(
            auth_path,
            json.dumps(auth, ensure_ascii=False, indent=2) + "\n",
            private=True,
        )


def remove_provider(cli: str, provider_id: str = "") -> ManagedFile:
    """Take AstrBot's configuration back out, leaving the user's own.

    Restores the pre-AstrBot file when there is a backup, because that is the
    only record of what the user had before; otherwise it removes just the keys
    AstrBot wrote.  A provider id drops that provider's stored credential too.
    """
    if cli not in CODING_GLOBAL_AGENT_TYPES:
        raise ValueError(f"Unknown coding agent type: {cli!r}")
    path = target_path(cli)

    if provider_id:
        _drop_credentials_for(provider_id)
        # The config file still names the section; whether to clear it is the
        # caller's choice, so nothing else changes here.
        return read_state(cli)

    backup = _backup_path(path)
    if backup.is_file():
        _atomic_write(path, backup.read_text(encoding="utf-8"), private=False)
        backup.unlink()
        # The backup restores the config file only; a credential lives in
        # auth.json, which AstrBot has no earlier version of to put back.
        if cli == "codex":
            _drop_stored_credentials()
        return read_state(cli)

    if not path.is_file():
        return read_state(cli)

    if cli == "claude_code":
        payload = _read_json(path)
        env = payload.get("env")
        if isinstance(env, Mapping):
            env = dict(env)
            for key in (
                "ANTHROPIC_BASE_URL",
                "ANTHROPIC_MODEL",
                "ANTHROPIC_AUTH_TOKEN",
            ):
                env.pop(key, None)
            if env:
                payload["env"] = env
            else:
                payload.pop("env", None)
        _atomic_write(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            private=False,
        )
        return read_state(cli)

    _atomic_write(
        path,
        _strip_managed_block(path.read_text(encoding="utf-8", errors="replace")),
        private=False,
    )
    _drop_stored_credentials()
    return read_state(cli)


def _drop_credentials_for(provider_id: str) -> None:
    """Forget one provider's stored credential."""
    auth_path = codex_home() / CODEX_AUTH_FILE
    if not auth_path.is_file():
        return
    auth = _read_json(auth_path)
    key = credential_env_name(provider_id)
    if key not in auth:
        return
    auth.pop(key, None)
    _atomic_write(
        auth_path,
        json.dumps(auth, ensure_ascii=False, indent=2) + "\n",
        private=True,
    )


def _drop_stored_credentials() -> None:
    """Remove every Codex credential AstrBot put in ``auth.json``.

    Matched on the section's own prefix rather than on a name built from one
    provider id: the section may name a variable an earlier version wrote, and
    leaving a key behind is the one outcome worth being wide about.
    """
    auth_path = codex_home() / CODEX_AUTH_FILE
    if not auth_path.is_file():
        return
    auth = _read_json(auth_path)
    stored = [key for key in auth if key.upper().startswith(_CODEX_KEY_PREFIX)]
    if not stored:
        return
    for key in stored:
        auth.pop(key, None)
    _atomic_write(
        auth_path,
        json.dumps(auth, ensure_ascii=False, indent=2) + "\n",
        private=True,
    )
