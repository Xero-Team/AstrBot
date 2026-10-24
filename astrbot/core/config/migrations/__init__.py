"""Forward-only migrations for the core configuration file.

The config store is a JSON document, so its applied state is a single
monotonic ``schema_revision`` integer kept inside the document, with the same
semantics as the SQLite ledger. Steps are conservative: an old flat key is
moved to its grouped location only when the grouped key is absent, so a user's
value survives the rename.
"""

from __future__ import annotations

CONFIG_SCHEMA_REVISION = 5


class ConfigMigrationError(RuntimeError):
    """Raised when the configuration cannot be migrated safely."""


# Flat key -> (group, grouped key)
_FLAT_KEY_MOVES: dict[str, tuple[str, str]] = {
    "log_level": ("log", "level"),
    "log_file_enable": ("log", "file_enable"),
    "log_file_path": ("log", "file_path"),
    "log_file_max_mb": ("log", "file_max_mb"),
    "trace_enable": ("trace", "enable"),
    "trace_log_enable": ("trace", "log_enable"),
    "trace_log_path": ("trace", "log_path"),
    "trace_log_max_mb": ("trace", "log_max_mb"),
    "t2i_word_threshold": ("t2i", "word_threshold"),
    "t2i_use_file_service": ("t2i", "use_file_service"),
    "t2i_active_template": ("t2i", "active_template"),
    "t2i_forward_card": ("t2i", "forward_card"),
    "kb_names": ("knowledge_base", "names"),
    "kb_fusion_top_k": ("knowledge_base", "fusion_top_k"),
    "kb_final_top_k": ("knowledge_base", "final_top_k"),
    "kb_agentic_mode": ("knowledge_base", "agentic_mode"),
}

_GROUPS = ("log", "trace", "t2i", "knowledge_base")


def _migrate_flat_to_grouped(conf: dict) -> bool:
    """Move flat keys into their grouped sections, preserving values."""
    changed = False
    grouped: dict[str, dict] = {}
    for group in _GROUPS:
        parent = conf.get(group)
        grouped[group] = dict(parent) if isinstance(parent, dict) else {}

    # The pre-grouping t2i flag was a top-level bool.
    if isinstance(conf.get("t2i"), bool):
        if grouped["t2i"].get("enable") is None:
            grouped["t2i"]["enable"] = conf.pop("t2i")
        else:
            conf.pop("t2i")
        changed = True

    for old_key, (group, new_key) in _FLAT_KEY_MOVES.items():
        if old_key not in conf:
            continue
        # A grouped key that is null counts as unset: keep the legacy value.
        if grouped[group].get(new_key) is None:
            grouped[group][new_key] = conf.pop(old_key)
        else:
            conf.pop(old_key)
        changed = True

    if not changed:
        return False

    for group in _GROUPS:
        if grouped[group]:
            conf[group] = grouped[group]
    return True


def _migrate_retired_gemini_embedding_model(conf: dict) -> bool:
    """Replace the retired Gemini embedding model in saved provider configs."""
    providers = conf.get("provider")
    if not isinstance(providers, list):
        return False

    changed = False
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if (
            provider.get("type") == "gemini_embedding"
            and provider.get("embedding_model") == "gemini-embedding-exp-03-07"
        ):
            provider["embedding_model"] = "gemini-embedding-001"
            changed = True
    return changed


def _migrate_trace_storage(conf: dict) -> bool:
    """Move trace file settings to the bounded SQLite storage budget."""
    trace = conf.get("trace")
    if not isinstance(trace, dict):
        return False
    old_keys = ("log_enable", "log_path", "log_max_mb")
    if not any(key in trace for key in old_keys):
        return False
    size = trace.get("log_max_mb")
    if trace.get("db_max_mb") is None:
        trace["db_max_mb"] = (
            size * 4
            if isinstance(size, int) and not isinstance(size, bool) and size > 0
            else 80
        )
    trace.setdefault("db_path", "logs/traces.db")
    trace.setdefault("retention_days", 7)
    for key in old_keys:
        trace.pop(key, None)
    return True


def _migrate_retired_computer_use_runtime(conf: dict) -> bool:
    """Fail closed after removing the remote sandbox runtimes."""
    changed = False
    provider_settings = conf.get("provider_settings")
    if isinstance(provider_settings, dict):
        if provider_settings.get("computer_use_runtime") == "sandbox":
            provider_settings["computer_use_runtime"] = "none"
            changed = True
        if "sandbox" in provider_settings:
            provider_settings.pop("sandbox", None)
            changed = True

    btw = conf.get("btw")
    work_loop = btw.get("work_loop") if isinstance(btw, dict) else None
    if (
        isinstance(work_loop, dict)
        and work_loop.get("computer_use_runtime") == "sandbox"
    ):
        work_loop["computer_use_runtime"] = "none"
        changed = True
    return changed


def migrate_config_dict(conf: dict) -> bool:
    """Bring a raw configuration document to the current revision.

    Args:
        conf: Mutable configuration loaded from disk.

    Returns:
        Whether the configuration changed.

    Raises:
        ConfigMigrationError: When ``schema_revision`` is newer than this build,
            because continuing would let integrity checking drop keys the writer
            did not understand.
    """
    revision = conf.get("schema_revision")
    # ``isinstance(True, int)`` is true, and a string or negative value is not a
    # revision; treat all of those as "no recorded revision" and migrate.
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        revision = 0

    if revision > CONFIG_SCHEMA_REVISION:
        raise ConfigMigrationError(
            f"configuration schema_revision {revision} is newer than this build's "
            f"{CONFIG_SCHEMA_REVISION}; upgrade the application or restore a backup",
        )

    changed = False
    while revision < CONFIG_SCHEMA_REVISION:
        if revision == 0:
            changed |= _migrate_flat_to_grouped(conf)
        elif revision == 1:
            changed |= _migrate_retired_gemini_embedding_model(conf)
        elif revision == 2:
            # Revision 3 unifies Local permission defaults for fresh installs,
            # but saved policies must not be rewritten: the legacy Windows
            # member default ("none") is indistinguishable from an explicit
            # opt-out, so preserve the document as written.
            pass
        elif revision == 3:
            changed |= _migrate_trace_storage(conf)
        elif revision == 4:
            changed |= _migrate_retired_computer_use_runtime(conf)
        revision += 1
        changed = True

    conf["schema_revision"] = revision
    return changed


__all__ = [
    "CONFIG_SCHEMA_REVISION",
    "ConfigMigrationError",
    "migrate_config_dict",
]
