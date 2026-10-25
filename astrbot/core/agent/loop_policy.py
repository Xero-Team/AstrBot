"""Loop-level policy shared by the default agent and the opt-in BTW loops.

The default conversation path only needs to know whether a profile enables the
work loop and what that loop is allowed to do. Keeping those decisions here
lets the default runtime avoid importing the BTW package.
"""

from collections.abc import Mapping

LOOP_CONVERSATION = "conversation"
LOOP_WORK = "work"


def loop_mode_of(value: object) -> str:
    """Return the loop a marker selects, defaulting to conversation."""
    return LOOP_WORK if value == LOOP_WORK else LOOP_CONVERSATION


def btw_config(config: object) -> Mapping:
    """Return the profile's BTW mapping, or an empty mapping.

    Args:
        config: A profile-like mapping.

    Returns:
        The ``btw`` mapping when it is a mapping, otherwise ``{}``.
    """
    if not isinstance(config, Mapping):
        return {}
    value = config.get("btw", {})
    return value if isinstance(value, Mapping) else {}


def is_btw_enabled(config: object) -> bool:
    """Return whether a profile explicitly enables BTW."""
    return bool(btw_config(config).get("enabled", False))


def is_work_loop_enabled(config: object) -> bool:
    """Return whether the profile explicitly enables BTW and work."""
    btw = btw_config(config)
    if not btw.get("enabled", False):
        return False
    work = btw.get("work_loop", {})
    return isinstance(work, Mapping) and bool(work.get("enabled", False))


COMPUTER_USE_RUNTIMES = frozenset({"none", "local"})


def normalize_computer_use_runtime(value: object) -> str:
    """Normalize an untrusted runtime value to the supported set.

    Per-profile configuration files do not pass through the main config
    migration, so a legacy ``sandbox`` value or an unknown string must fail
    closed to ``none`` rather than reaching a host-level runtime.
    """
    return (
        value if isinstance(value, str) and value in COMPUTER_USE_RUNTIMES else "none"
    )


def resolve_computer_runtime(
    profile: Mapping,
    loop: object,
    inherited: str,
) -> str:
    """Resolve the runtime without granting any tool authorization.

    Args:
        profile: The current configuration profile.
        loop: The event's loop marker; only ``work`` selects the work loop.
        inherited: The runtime selected before applying BTW settings.

    Returns:
        The inherited runtime when BTW is disabled, otherwise the permitted
        runtime for this loop.
    """
    inherited = normalize_computer_use_runtime(inherited)
    btw = profile.get("btw", {})
    if not isinstance(btw, Mapping) or not btw.get("enabled", False):
        return inherited
    if loop != LOOP_WORK:
        return "none"
    work = btw.get("work_loop", {})
    runtime = (
        work.get("computer_use_runtime", "inherit")
        if isinstance(work, Mapping)
        else "inherit"
    )
    if runtime == "inherit":
        return inherited
    return normalize_computer_use_runtime(runtime)


def work_loop_is_read_only(profile: Mapping, loop: object) -> bool:
    """Return whether the work loop must run without write-capable tools.

    The work loop plans and reads; anything that changes state is delegated to
    a coding agent, so the flag defaults to on.  It is a restriction of the
    capabilities the profile already grants -- never a grant of its own.

    Args:
        profile: The current configuration profile.
        loop: The event's loop marker; only ``work`` can be read-only.

    Returns:
        Whether the work loop's tool catalog must drop write-capable tools.
    """
    btw = profile.get("btw", {})
    if not isinstance(btw, Mapping) or not btw.get("enabled", False):
        return False
    if loop != LOOP_WORK:
        return False
    work = btw.get("work_loop", {})
    if not isinstance(work, Mapping):
        return True
    return bool(work.get("read_only", True))


def route_is_available_in_loop(
    routes: object,
    *,
    route_key: str,
    route_id: str,
    loop_mode: str,
    default_loop: str = "both",
) -> bool:
    """Resolve a list assignment, falling back to the capability's default.

    Args:
        routes: List of dictionaries containing the capability key and ``loop``.
        route_key: Key identifying a capability in an assignment.
        route_id: Capability identifier to look up.
        loop_mode: Current loop; missing or invalid values mean conversation.
        default_loop: Assignment used for missing or malformed entries.

    Returns:
        Whether the capability is available in the current loop.
    """
    loop_mode = loop_mode_of(loop_mode)
    route = default_loop
    if isinstance(routes, list):
        for entry in routes:
            if not isinstance(entry, dict) or entry.get(route_key) != route_id:
                continue
            candidate = entry.get("loop")
            if isinstance(candidate, str) and candidate in {
                "conversation",
                "work",
                "both",
            }:
                route = candidate
            break
    return route in {"both", loop_mode}
