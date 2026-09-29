"""Forward-only migrations for the core configuration file.

The config store is a JSON document, so its applied state is a single
monotonic ``schema_revision`` integer kept inside the document, with the same
semantics as the SQLite ledger. Steps are conservative: an old flat key is
moved to its grouped location only when the grouped key is absent, so a user's
value survives the rename.
"""

from __future__ import annotations

CONFIG_SCHEMA_REVISION = 1


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

    if revision >= CONFIG_SCHEMA_REVISION:
        return False

    _migrate_flat_to_grouped(conf)
    conf["schema_revision"] = CONFIG_SCHEMA_REVISION
    return True


__all__ = [
    "CONFIG_SCHEMA_REVISION",
    "ConfigMigrationError",
    "migrate_config_dict",
]
