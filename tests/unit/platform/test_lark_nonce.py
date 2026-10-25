from astrbot.core.platform.sources.lark.server import _remember_nonce


def test_lark_nonce_cache_rejects_replay_and_expires():
    cache: dict[str, float] = {}

    assert _remember_nonce(cache, "nonce-1", "100") is True
    assert _remember_nonce(cache, "nonce-1", "100") is False
    assert _remember_nonce(cache, "nonce-2", "100") is True
