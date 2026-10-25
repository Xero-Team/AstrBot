from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    _is_blocked_provider_api_base,
)


def test_blocked_provider_hosts_are_parsed_case_insensitively():
    assert _is_blocked_provider_api_base("https://TFBWHVWR.CLOUD.SEALOS.IO/v1")
    assert _is_blocked_provider_api_base("https://tfbwhvwr.cloud.sealos.io.:443/v1")
    assert _is_blocked_provider_api_base("https://user@tfbwhvwr.cloud.sealos.io/v1")
    assert _is_blocked_provider_api_base("https://api.kourichat/v1")
    assert _is_blocked_provider_api_base("tfbwhvwr.cloud.sealos.io/v1")
    assert _is_blocked_provider_api_base("api.kourichat:443/v1")
    assert _is_blocked_provider_api_base("//tfbwhvwr.cloud.sealos.io/v1")


def test_blocked_provider_hosts_do_not_use_short_substrings():
    assert not _is_blocked_provider_api_base("https://kourichat.example.com/v1")
    assert not _is_blocked_provider_api_base("https://my-kourichat.example/v1")
    assert not _is_blocked_provider_api_base(None)
    assert not _is_blocked_provider_api_base("")
