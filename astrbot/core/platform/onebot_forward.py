"""Bounded, failure-tolerant expansion of OneBot v11 merged forwards.

Unexpanded merged forwards arrive from OneBot v11 backends as an id-only
``Forward`` (``content is None``).  This helper lets a source adapter populate
that content through its ``get_forward_msg`` action before the event is
committed.  Any fetch or parse failure preserves the original component and no
exception escapes ingress.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence

from astrbot.core.message.components import (
    BaseMessageComponent,
    Forward,
    Node,
    Nodes,
)

DEFAULT_MAX_FETCH = 8
DEFAULT_FETCH_TIMEOUT = 5.0

ForwardFetch = Callable[[str], Awaitable[Mapping[str, object] | None]]
ForwardParse = Callable[[Mapping[str, object]], Awaitable[list[BaseMessageComponent]]]


async def expand_unexpanded_forwards(
    components: Sequence[BaseMessageComponent],
    *,
    fetch: ForwardFetch,
    parse: ForwardParse,
    max_fetch: int = DEFAULT_MAX_FETCH,
    timeout: float = DEFAULT_FETCH_TIMEOUT,  # noqa: ASYNC109
) -> list[BaseMessageComponent]:
    """Expand id-only forwards in ``components`` from the source adapter.

    Nested id-only forwards are expanded recursively until ``max_fetch`` fetches
    are exhausted, and each distinct forward id is fetched at most once.  A
    fetch/parse failure, timeout, empty result, or exhausted budget leaves the
    original ``Forward`` untouched.

    Args:
        components: Inbound components to walk.
        fetch: Coroutine returning the raw ``get_forward_msg`` payload for an id.
        parse: Coroutine converting that payload into node components.
        max_fetch: Maximum number of distinct forward ids to fetch.
        timeout: Per fetch/parse timeout in seconds.

    Returns:
        A new component list with expanded forwards substituted in place.
    """
    if max_fetch <= 0:
        return list(components)

    cache: dict[str, list[BaseMessageComponent] | None] = {}
    remaining = max_fetch

    async def fetch_nodes(forward_id: str) -> list[BaseMessageComponent] | None:
        nonlocal remaining
        if forward_id in cache:
            return cache[forward_id]
        if remaining <= 0:
            return None
        remaining -= 1
        try:
            payload = await asyncio.wait_for(fetch(forward_id), timeout=timeout)
            if not payload:
                cache[forward_id] = None
                return None
            nodes = await asyncio.wait_for(parse(payload), timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception:
            cache[forward_id] = None
            return None
        if not nodes:
            cache[forward_id] = None
            return None
        expanded = await expand_nodes(nodes)
        cache[forward_id] = expanded
        return expanded

    async def expand_nodes(
        items: Sequence[BaseMessageComponent],
    ) -> list[BaseMessageComponent]:
        result: list[BaseMessageComponent] = []
        for item in items:
            if isinstance(item, Forward) and not item.content:
                expanded = await fetch_nodes(str(item.id))
                if expanded:
                    result.append(item.model_copy(update={"content": expanded}))
                else:
                    result.append(item)
            elif isinstance(item, Nodes):
                result.append(
                    item.model_copy(update={"nodes": await expand_nodes(item.nodes)})
                )
            elif isinstance(item, Node):
                result.append(
                    item.model_copy(
                        update={"content": await expand_nodes(item.content)}
                    )
                )
            else:
                result.append(item)
        return result

    return await expand_nodes(list(components))


__all__ = [
    "DEFAULT_FETCH_TIMEOUT",
    "DEFAULT_MAX_FETCH",
    "ForwardFetch",
    "ForwardParse",
    "expand_unexpanded_forwards",
]
