"""Configuration and command lines for the coding agents the work loop delegates to.

The work loop reads and plans; anything that has to write is handed to a
coding agent CLI that runs in the task's own folder.  This module owns both
halves of that contract -- what the profile configures and what the CLI is
launched with -- so the config schema and the command line cannot drift apart.

Provider presets follow cc-switch: each agent carries a list of providers and
one active provider, and the active one is handed to the CLI in that CLI's own
config format.  The generated file is a layer the CLI loads in addition to the
user's own configuration (``--settings`` for Claude Code, ``--profile`` for
Codex), so switching providers never rewrites the CLI config the user runs
interactively.
"""

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from astrbot import logger
from astrbot.core.agent.btw.types import is_work_loop_enabled
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.config_number import coerce_int_config

CODING_AGENT_TYPES = ("claude_code", "codex", "custom")

DEFAULT_COMMANDS = {"claude_code": "claude", "codex": "codex", "custom": ""}

# Permission choices each CLI accepts for a non-interactive run.  The defaults
# write only where the task is allowed to write and never reach the host's own
# files, so an operator can run a delegated task without reviewing it first.
CLAUDE_PERMISSION_MODES = (
    "acceptEdits",
    "auto",
    "bypassPermissions",
    "manual",
    "dontAsk",
    "plan",
)
CODEX_SANDBOXES = ("read-only", "workspace-write", "danger-full-access")
DEFAULT_PERMISSION_MODE = "acceptEdits"
DEFAULT_SANDBOX = "workspace-write"

DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_MAX_OUTPUT_CHARS = 20000
MIN_TIMEOUT_SECONDS = 1
MIN_MAX_OUTPUT_CHARS = 200

CODEX_PROFILE_NAME = "astrbot-btw"
CODEX_PROVIDER_ID = "astrbot_btw"

TASK_FILE_NAME = "TASK.md"
# Codex can write its final message to a file, which survives a run whose JSON
# stream was cut short.
LAST_MESSAGE_NAME = "last_message.txt"


@dataclass(frozen=True, slots=True)
class CodingInvocation:
    """One prepared coding-agent run.

    Attributes:
        argv: The command line, with the prompt read from the child's stdin.
        env: Environment entries to add to the parent environment.
        cwd: The task folder the CLI runs in.
        settings_path: The generated CLI config layer, when the active provider
            needed one.
    """

    argv: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path = Path()
    settings_path: Path | None = None


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _flag(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _env_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str) and key and isinstance(item, str)
    }


def _normalize_providers(raw: object) -> list[dict]:
    """Return the provider presets an agent can switch between."""
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
                "base_url": _text(entry.get("base_url")).strip(),
                "api_key": _text(entry.get("api_key")).strip(),
                "model": _text(entry.get("model")).strip(),
                "wire_api": _text(entry.get("wire_api"), "responses").strip()
                or "responses",
            }
        )
    return providers


def _normalize_agent(entry: object) -> dict | None:
    """Return one usable agent entry, or ``None`` when it cannot be used.

    A malformed entry is dropped rather than raised: the list comes from a
    profile, and one bad entry must not stop the remaining agents from working.
    """
    if not isinstance(entry, Mapping):
        return None
    agent_id = _text(entry.get("id")).strip()
    agent_type = _text(entry.get("type")).strip()
    if not agent_id or agent_type not in CODING_AGENT_TYPES:
        return None
    command = _text(entry.get("command")).strip() or DEFAULT_COMMANDS[agent_type]
    if not command:
        return None
    providers = _normalize_providers(entry.get("providers"))
    provider_ids = {provider["id"] for provider in providers}
    active_provider = _text(entry.get("active_provider")).strip()
    if active_provider not in provider_ids:
        active_provider = providers[0]["id"] if providers else ""
    permission_mode = _text(entry.get("permission_mode")).strip()
    if permission_mode not in CLAUDE_PERMISSION_MODES:
        permission_mode = DEFAULT_PERMISSION_MODE
    sandbox = _text(entry.get("sandbox")).strip()
    if sandbox not in CODEX_SANDBOXES:
        sandbox = DEFAULT_SANDBOX
    return {
        "id": agent_id,
        "name": _text(entry.get("name"), agent_id).strip() or agent_id,
        "type": agent_type,
        "enabled": _flag(entry.get("enabled")),
        "command": command,
        "model": _text(entry.get("model")).strip(),
        "permission_mode": permission_mode,
        "sandbox": sandbox,
        "project_dir": _text(entry.get("project_dir")).strip(),
        "extra_args": _text_list(entry.get("extra_args")),
        "env": _env_map(entry.get("env")),
        "timeout_seconds": coerce_int_config(
            entry.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS,
            default=DEFAULT_TIMEOUT_SECONDS,
            min_value=MIN_TIMEOUT_SECONDS,
            field_name="timeout_seconds",
            source=f"Coding agent {agent_id}",
        ),
        "max_output_chars": coerce_int_config(
            entry.get("max_output_chars") or DEFAULT_MAX_OUTPUT_CHARS,
            default=DEFAULT_MAX_OUTPUT_CHARS,
            min_value=MIN_MAX_OUTPUT_CHARS,
            field_name="max_output_chars",
            source=f"Coding agent {agent_id}",
        ),
        "active_provider": active_provider,
        "providers": providers,
    }


def normalize_coding_agents(raw: object) -> list[dict]:
    """Return the valid coding-agent entries of a profile, in order.

    Args:
        raw: The untrusted ``btw.work_loop.coding_agents`` value.

    Returns:
        One normalized entry per usable agent, with duplicate ids dropped.
    """
    agents: list[dict] = []
    seen: set[str] = set()
    for entry in raw if isinstance(raw, list) else []:
        agent = _normalize_agent(entry)
        if agent is None or agent["id"] in seen:
            continue
        seen.add(agent["id"])
        agents.append(agent)
    return agents


def enabled_coding_agents(profile: Mapping) -> list[dict]:
    """Return the enabled coding agents of an enabled, delegating work loop.

    Delegation needs the work loop's Computer Use runtime to be ``local``.
    A delegated run is a process on this host, started by AstrBot directly
    rather than through the Computer Use booter, so it is not inside whatever
    boundary a ``sandbox`` work loop would put an ordinary shell in; letting it
    run there would be the way out of the sandbox rather than a use of it.
    ``inherit`` resolves to ``none`` until the request is built, so it does not
    select here either.
    """
    btw = profile.get("btw", {}) if isinstance(profile, Mapping) else {}
    work = btw.get("work_loop", {}) if isinstance(btw, Mapping) else {}
    if not is_work_loop_enabled(profile):
        return []
    if not isinstance(work, Mapping):
        return []
    if work.get("computer_use_runtime", "inherit") != "local":
        return []
    return [
        agent
        for agent in normalize_coding_agents(work.get("coding_agents"))
        if agent["enabled"]
    ]


def has_enabled_coding_agent(profile: object) -> bool:
    """Return whether a profile offers a coding agent to delegate to."""
    if not isinstance(profile, Mapping):
        return False
    return bool(enabled_coding_agents(profile))


def select_coding_agent(profile: Mapping, agent_id: str = "") -> dict | None:
    """Return the requested agent, or the first enabled one when unnamed.

    Args:
        profile: The current configuration profile.
        agent_id: The requested agent id; empty selects the first enabled one.

    Returns:
        The matching agent, or ``None`` when no enabled agent matches.
    """
    agents = enabled_coding_agents(profile)
    wanted = agent_id.strip()
    if not wanted:
        return agents[0] if agents else None
    for agent in agents:
        if agent["id"] == wanted:
            return agent
    return None


def active_provider(agent: Mapping) -> dict | None:
    """Return the provider an agent is currently pointed at."""
    active = agent.get("active_provider", "")
    for provider in agent.get("providers", []):
        if provider["id"] == active:
            return provider
    return None


def settings_home(agent: Mapping) -> Path:
    """Return the AstrBot-owned directory holding one agent's generated config."""
    root = Path(get_astrbot_data_path()) / "btw" / "coding-agents"
    return root / str(agent.get("id", "agent"))


def _profile_home() -> Path:
    """Return the Codex home the generated profile layer is written into."""
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def agent_id_slug(agent_id: object) -> str:
    """Return the filesystem-safe form of an agent id.

    The id comes from a profile, so it is sanitized rather than trusted: it
    names generated files, and a configured id must not be able to place them
    outside the directory they belong in.
    """
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(agent_id or "agent")).strip("-.")
    return safe[:64] or "agent"


def codex_profile_path(agent: Mapping) -> Path:
    """Return the Codex config layer one agent's provider is written to.

    Each agent gets its own file.  A single shared file would have two agents
    running at once overwrite each other's provider, because the settings are
    written before the run and read by the CLI while it runs.
    """
    name = f"{CODEX_PROFILE_NAME}-{agent_id_slug(agent.get('id'))}"
    return _profile_home() / f"{name}.config.toml"


def codex_profile_name(agent: Mapping) -> str:
    """Return the ``--profile`` name that selects one agent's Codex layer."""
    return f"{CODEX_PROFILE_NAME}-{agent_id_slug(agent.get('id'))}"


def codex_credential_env_name(agent: Mapping) -> str:
    """Return the environment variable one agent's Codex layer reads its key from.

    The name is per agent because only one Codex profile is layered per run:
    two agents started together hold different keys, and a shared variable name
    would let the later child's export decide which key the earlier one uses.
    """
    return f"ASTRBOT_BTW_CODEX_KEY_{agent_id_slug(agent.get('id')).upper().replace('-', '_')}"


def _write_json(path: Path, payload: dict) -> None:
    """Replace a JSON file atomically so a reader never sees a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _write_text(path: Path, text: str) -> None:
    """Replace a text file atomically so a reader never sees a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _claude_settings(agent: Mapping, provider: Mapping) -> tuple[Path, dict[str, str]]:
    """Write the Claude Code settings layer for one provider.

    The layer carries the endpoint and the model: neither is a secret, and
    together they make the CLI usable outside AstrBot as well.  The credential
    travels in the child's environment instead, because Claude Code reads it
    from there, and a key written to a file outlives the run that needed it.
    """
    # Read the endpoint and the model without ever holding the credential in
    # the same value: what this function writes must not be able to carry it.
    base_url = str(provider.get("base_url", ""))
    model = str(provider.get("model", "")) or str(agent.get("model", ""))
    layer = {"ANTHROPIC_BASE_URL": base_url}
    if model:
        layer["ANTHROPIC_MODEL"] = model
    path = settings_home(agent) / "claude-settings.json"
    _write_json(path, {"env": {key: value for key, value in layer.items() if value}})
    env = {key: value for key, value in layer.items() if value}
    api_key = str(provider.get("api_key", ""))
    if api_key:
        env["ANTHROPIC_AUTH_TOKEN"] = api_key
    return path, env


def _codex_profile(agent: Mapping, provider: Mapping) -> tuple[Path, dict[str, str]]:
    """Write the Codex config layer for one provider.

    Codex layers ``$CODEX_HOME/<name>.config.toml`` over the user's own config,
    and reads the provider credential from the environment variable the layer
    names, so the user's ``config.toml`` and ``auth.json`` stay untouched.

    The layer is named for the agent: several agents may run at once, and one
    shared file would have each run overwrite the other's provider.
    """
    base_url = str(provider.get("base_url", ""))
    name = str(provider.get("name", "")) or "AstrBot BTW"
    model = str(provider.get("model", "")) or str(agent.get("model", ""))
    credential_env = codex_credential_env_name(agent)
    lines = [f"model_provider = {json.dumps(CODEX_PROVIDER_ID)}"]
    if model:
        lines.append(f"model = {json.dumps(model)}")
    lines.append("")
    lines.append(f"[model_providers.{CODEX_PROVIDER_ID}]")
    lines.append(f"name = {json.dumps(name)}")
    lines.append(f"base_url = {json.dumps(base_url)}")
    lines.append(f'env_key = "{credential_env}"')
    lines.append(f"wire_api = {json.dumps(str(provider.get('wire_api', 'responses')))}")
    path = codex_profile_path(agent)
    _write_text(path, "\n".join(lines) + "\n")
    return path, {credential_env: str(provider.get("api_key", ""))}


def _settings_layer(agent: Mapping, provider: Mapping) -> tuple[Path, dict[str, str]]:
    """Write the CLI config layer that makes one provider take effect."""
    if agent.get("type") == "codex":
        return _codex_profile(agent, provider)
    return _claude_settings(agent, provider)


def _provider_is_configured(agent: Mapping, provider: Mapping | None) -> bool:
    """Return whether a provider needs a config layer this module can write.

    Two presets need none.  An "official login" preset carries neither an
    endpoint nor a credential, so the CLI falls back to the account the user
    already signed in with.  A ``custom`` agent runs a CLI whose config format
    this module does not know, so it states its own credentials through the
    agent's ``env`` map rather than through a file it would never read.

    Args:
        agent: A normalized coding-agent entry.
        provider: The agent's active provider, when it has one.

    Returns:
        Whether the run needs a generated config layer.
    """
    if provider is None or agent.get("type") == "custom":
        return False
    if str(provider.get("base_url", "")) or str(provider.get("api_key", "")):
        return True
    if agent.get("type") == "codex":
        return bool(provider.get("model")) or bool(agent.get("model"))
    return False


def build_invocation(
    agent: Mapping,
    *,
    workspace: Path,
) -> CodingInvocation:
    """Prepare one coding-agent run inside a task folder.

    The prompt travels on the child's stdin so a long task never meets a
    platform command-line limit, and the same text is kept in the task folder
    for the operator to read afterwards.

    Args:
        agent: A normalized coding-agent entry.
        workspace: The task folder the CLI runs in.

    Returns:
        The command line, environment additions, working directory, and the
        generated settings layer when the provider needed one.
    """
    agent_type = str(agent.get("type", ""))
    provider = active_provider(agent)
    settings_path: Path | None = None
    if _provider_is_configured(agent, provider):
        assert provider is not None
        settings_path, provider_env = _settings_layer(agent, provider)
    else:
        provider_env = {}
    command = str(agent.get("command", ""))
    extra_args = [str(item) for item in agent.get("extra_args", [])]
    argv: list[str] = []
    env: dict[str, str] = dict(agent.get("env", {}))
    env.update({key: value for key, value in provider_env.items() if value})

    if agent_type == "claude_code":
        argv = [command, "-p", "--output-format", "stream-json", "--verbose"]
        # ``extra_args`` come before the flags this module manages, because a
        # CLI resolves a repeated flag in favour of the last one: the profile
        # may extend the run, but it may not talk the managed permission mode
        # or settings layer back down.
        argv += extra_args
        argv += ["--permission-mode", str(agent.get("permission_mode"))]
        if model := str(agent.get("model", "")):
            argv += ["--model", model]
        if project_dir := str(agent.get("project_dir", "")):
            argv += ["--add-dir", project_dir]
        if settings_path is not None:
            argv += ["--settings", str(settings_path)]
    elif agent_type == "codex":
        argv = [command, "exec", "--json", "--cd", str(workspace)]
        argv += extra_args
        argv += ["--sandbox", str(agent.get("sandbox"))]
        argv += ["--skip-git-repo-check"]
        argv += ["-o", str(workspace / LAST_MESSAGE_NAME)]
        if model := str(agent.get("model", "")):
            argv += ["--model", model]
        if project_dir := str(agent.get("project_dir", "")):
            argv += ["--add-dir", project_dir]
        if settings_path is not None:
            argv += ["--profile", codex_profile_name(agent)]
    else:
        argv = [command]
        argv += extra_args

    return CodingInvocation(
        argv=tuple(argv),
        env=env,
        cwd=workspace,
        settings_path=settings_path,
    )


def _claude_result_text(stdout: str) -> str:
    """Return the final message of a Claude Code ``stream-json`` run."""
    text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if not isinstance(payload, dict) or payload.get("type") != "result":
            continue
        if payload.get("is_error"):
            logger.warning("Claude Code reported an error result.")
        result = payload.get("result")
        if isinstance(result, str) and result.strip():
            text = result.strip()
    return text


def _codex_result_text(stdout: str) -> str:
    """Return the final message of a Codex ``--json`` run."""
    text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        item = payload.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        message = item.get("text")
        if isinstance(message, str) and message.strip():
            text = message.strip()
    return text


def agent_result_text(agent: Mapping, stdout: str, last_message: str = "") -> str:
    """Return the coding agent's own final message.

    Codex can write its final message to a file, which survives a run whose
    JSON stream was truncated; the stream is the fallback for both CLIs.
    """
    agent_type = str(agent.get("type", ""))
    if agent_type == "codex":
        return last_message.strip() or _codex_result_text(stdout)
    if agent_type == "claude_code":
        return _claude_result_text(stdout)
    return ""


def truncate_output(text: str, limit: int) -> str:
    """Return ``text`` capped at ``limit`` characters, marking the cut."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[{len(text) - limit} characters truncated]"
