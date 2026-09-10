"""Computer runtime selection for BTW requests and their handoffs."""

from collections.abc import Mapping


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
    btw = profile.get("btw", {})
    if not isinstance(btw, Mapping) or not btw.get("enabled", False):
        return inherited
    if loop != "work":
        return "none"
    work = btw.get("work_loop", {})
    runtime = (
        work.get("computer_use_runtime", "inherit")
        if isinstance(work, Mapping)
        else "inherit"
    )
    if runtime not in ("none", "local", "sandbox"):
        runtime = inherited
    return runtime if runtime in ("none", "local", "sandbox") else "none"
