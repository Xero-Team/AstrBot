"""Provider candidate normalization shared by request building and the runner."""

from types import SimpleNamespace

from astrbot.core.agent.provider_plan import ProviderPlan


def _provider(provider_id: str):
    return SimpleNamespace(provider_config={"id": provider_id})


def test_from_candidates_keeps_the_primary_and_ordered_unique_fallbacks():
    primary = _provider("primary")
    first = _provider("first")
    duplicate = _provider("first")
    second = _provider("second")

    plan = ProviderPlan.from_candidates(primary, [first, primary, duplicate, second])

    assert plan.primary is primary
    assert plan.fallbacks == (first, second)
    assert plan.candidates == (primary, first, second)


def test_from_candidates_keeps_fallbacks_without_an_id():
    primary = _provider("primary")
    first = _provider("")
    second = _provider("")

    plan = ProviderPlan.from_candidates(primary, [first, second])

    assert plan.fallbacks == (first, second)


def test_with_primary_removes_the_new_primary_from_fallbacks():
    primary = _provider("primary")
    promoted = _provider("promoted")
    other = _provider("other")
    plan = ProviderPlan.from_candidates(primary, [promoted, other])

    promoted_plan = plan.with_primary(promoted)

    assert promoted_plan.primary is promoted
    assert promoted_plan.fallbacks == (other,)
    assert promoted_plan.candidates == (promoted, other)


def test_with_primary_deduplicates_a_distinct_provider_with_the_same_id():
    primary = _provider("primary")
    promoted = _provider("promoted")
    duplicate = _provider("promoted")
    other = _provider("other")
    plan = ProviderPlan.from_candidates(primary, [promoted, duplicate, other])

    promoted_plan = plan.with_primary(duplicate)

    assert promoted_plan.primary is duplicate
    assert promoted_plan.fallbacks == (other,)
    assert promoted_plan.candidates == (duplicate, other)
