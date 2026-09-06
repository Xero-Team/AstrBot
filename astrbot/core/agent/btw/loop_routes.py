"""Shared BTW loop-route resolution.

Plugin, MCP, and Skill capability routes follow one matching rule. Keeping a
single narrow implementation here prevents duplicated drift between the main
agent assembly and the handoff tool executor.
"""


_LOOP_VALUES = {"conversation", "work"}
_ALLOWED_ROUTES = _LOOP_VALUES | {"both"}


def route_is_available_in_loop(
    routes: object,
    *,
    route_key: str,
    route_id: str,
    loop_mode: str,
    default_loop: str = "both",
) -> bool:
    """Return whether a configured capability is available in one BTW loop.

    Plugin and MCP callers use a work-only default so newly installed execution
    capabilities cannot silently enter the conversation loop. Skills keep the
    both-loop default because they inject instructions rather than execution
    privileges. An explicit route always wins.

    Args:
        routes: Saved route assignments (list of ``{route_key, loop}`` dicts,
            or a legacy ``{route_id: loop}`` dict).
        route_key: Assignment key identifying the capability.
        route_id: The capability's identifier.
        loop_mode: The loop asking for access (``conversation`` or ``work``).
        default_loop: The loop used when no assignment exists.

    Returns:
        Whether the capability is available in ``loop_mode``.
    """
    if loop_mode not in _LOOP_VALUES or not route_id:
        return True

    if default_loop not in _ALLOWED_ROUTES:
        default_loop = "work"
    route = default_loop
    if isinstance(routes, dict):
        candidate = routes.get(route_id, default_loop)
        route = candidate if isinstance(candidate, str) else default_loop
    elif isinstance(routes, list):
        for entry in routes:
            if not isinstance(entry, dict) or entry.get(route_key) != route_id:
                continue
            candidate = entry.get("loop", default_loop)
            route = candidate if isinstance(candidate, str) else default_loop
            break

    if route not in _ALLOWED_ROUTES:
        route = default_loop
    return route in {"both", loop_mode}
