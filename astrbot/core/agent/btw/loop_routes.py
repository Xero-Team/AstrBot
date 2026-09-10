"""Resolve capability assignments shared by BTW request paths."""


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
    loop_mode = "work" if loop_mode == "work" else "conversation"
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
