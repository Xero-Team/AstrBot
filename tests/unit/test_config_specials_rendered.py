"""Every config special the metadata declares can actually be rendered.

A `_special` name is a contract between the backend metadata and the Dashboard:
the metadata says "render this value with the editor named here", and
`ConfigItemRenderer.vue` is what has to know that name.  Nothing checks the two
agree, so a name with no branch falls through to the generic editor for the
item's `type` -- and for a list of objects that is a string-list editor, which
shows `[object Object]` and replaces the value with strings on save.  That is
how `select_coding_agents` was broken.
"""

import re
from pathlib import Path

import pytest

from astrbot.core.config import default as config_default

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = (
    REPO_ROOT / "dashboard" / "src" / "components" / "shared" / "ConfigItemRenderer.vue"
)

# Specials `ConfigItemRenderer.vue` handles without a template branch, because
# they change what another editor does rather than picking one.
ELSEWHERE = frozenset({"agent_runner_type"})


def _renderer_source() -> str:
    return RENDERER.read_text(encoding="utf-8")


def _template(source: str) -> str:
    """Return the renderer's template.

    Not a split on ``</template>``: each ``v-else-if`` branch is its own
    ``<template>`` element, so the first closing tag ends the first branch.
    """
    return source.split("<script", 1)[0]


def _rendered_specials() -> set[str]:
    """Return the specials with a branch in the renderer's template chain."""
    return set(
        re.findall(r"itemMeta\?\._special === '([^']+)'", _template(_renderer_source()))
    )


def _walk(node: object):
    """Yield every mapping in a metadata tree, however deeply nested."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _declared_specials() -> set[str]:
    """Return every `_special` a live metadata tree declares.

    The trees are walked rather than the source read, so a commented-out entry
    -- of which there are several -- does not count as a live contract.
    """
    names: set[str] = set()
    for tree in (
        config_default.CONFIG_METADATA_2,
        config_default.CONFIG_METADATA_3,
        config_default.CONFIG_METADATA_3_SYSTEM,
    ):
        for mapping in _walk(tree):
            special = mapping.get("_special")
            if isinstance(special, str) and special:
                names.add(special)
    return names


def test_the_metadata_still_declares_specials():
    """Guard the guard: a walk that finds nothing would pass vacuously."""
    assert len(_declared_specials()) > 5


def test_every_declared_special_has_a_renderer():
    missing = sorted(_declared_specials() - _rendered_specials() - ELSEWHERE)
    assert missing == [], (
        f"These _special names have no branch in {RENDERER.name}: {missing}. "
        "Add one, or list the name in ELSEWHERE with what handles it instead."
    )


@pytest.mark.parametrize("special", sorted(ELSEWHERE))
def test_an_exempt_special_is_still_handled(special):
    """An exemption is a claim that the renderer handles it some other way."""
    assert special in _renderer_source()
