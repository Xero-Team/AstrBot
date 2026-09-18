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
    if loop != "work":
        return False
    work = btw.get("work_loop", {})
    if not isinstance(work, Mapping):
        return True
    return bool(work.get("read_only", True))
