from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlmodel import select

from astrbot.core.agent.response import AgentStats
from astrbot.core.db.po import ProviderStat
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.provider.entities import ProviderRequest, TokenUsage


@pytest.mark.asyncio
async def test_record_internal_agent_stats_persists_provider_stat(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-42")
    req = ProviderRequest(
        conversation=SimpleNamespace(cid="conv-123"),
    )
    stats = AgentStats(
        token_usage=TokenUsage(input_other=11, input_cached=3, output=7),
        start_time=100.0,
        end_time=108.5,
        time_to_first_token=0.6,
    )
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=stats,
        was_aborted=lambda: False,
    )
    final_resp = SimpleNamespace(role="assistant")

    await internal._record_internal_agent_stats(
        event,
        req,
        agent_runner,
        final_resp,
        temp_db,
    )

    async with temp_db.get_db() as session:
        result = await session.execute(select(ProviderStat))
        records = result.scalars().all()

    assert len(records) == 1
    record = records[0]
    assert record.agent_type == "internal"
    assert record.status == "completed"
    assert record.umo == "webchat:FriendMessage:session-42"
    assert record.conversation_id == "conv-123"
    assert record.provider_id == "provider-1"
    assert record.provider_model == "gpt-4.1"
    assert record.token_input_other == 11
    assert record.token_input_cached == 3
    assert record.token_output == 7
    assert record.start_time == 100.0
    assert record.end_time == 108.5
    assert record.time_to_first_token == 0.6


@pytest.mark.asyncio
async def test_record_internal_agent_stats_marks_aborted_and_falls_back_to_meta_id(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-aborted")
    stats = AgentStats(token_usage=TokenUsage(output=2))
    provider = SimpleNamespace(
        provider_config={"id": ""},
        meta=lambda: SimpleNamespace(id="fallback-provider", type="openai"),
        get_model=lambda: "gpt-4.1-mini",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=stats,
        was_aborted=lambda: True,
    )

    await internal._record_internal_agent_stats(
        event,
        req=None,
        agent_runner=agent_runner,
        final_resp=SimpleNamespace(role="assistant"),
        db=temp_db,
    )

    async with temp_db.get_db() as session:
        result = await session.execute(select(ProviderStat))
        records = result.scalars().all()

    assert len(records) == 1
    record = records[0]
    assert record.status == "aborted"
    assert record.provider_id == "fallback-provider"
    assert record.conversation_id is None


@pytest.mark.asyncio
async def test_record_internal_agent_stats_marks_error_status_for_err_response(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-error")
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-error"))
    stats = AgentStats(token_usage=TokenUsage(input_other=1, output=1))
    provider = SimpleNamespace(
        provider_config={"id": "provider-error"},
        meta=lambda: SimpleNamespace(id="provider-error", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=stats,
        was_aborted=lambda: False,
    )

    await internal._record_internal_agent_stats(
        event,
        req=req,
        agent_runner=agent_runner,
        final_resp=SimpleNamespace(role="err"),
        db=temp_db,
    )

    async with temp_db.get_db() as session:
        result = await session.execute(select(ProviderStat))
        records = result.scalars().all()

    assert len(records) == 1
    assert records[0].status == "error"


@pytest.mark.asyncio
async def test_record_internal_agent_stats_swallows_insert_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    logger_warning = MagicMock()
    monkeypatch.setattr(internal.logger, "warning", logger_warning)

    async def raise_insert(*args, **kwargs):
        raise RuntimeError("db write failed")

    db = SimpleNamespace(insert_provider_stat=raise_insert)

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-warning")
    stats = AgentStats(token_usage=TokenUsage(output=1))
    provider = SimpleNamespace(
        provider_config={"id": "provider-warning"},
        meta=lambda: SimpleNamespace(id="provider-warning", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=stats,
        was_aborted=lambda: False,
    )

    await internal._record_internal_agent_stats(
        event,
        req=None,
        agent_runner=agent_runner,
        final_resp=SimpleNamespace(role="assistant"),
        db=db,
    )

    logger_warning.assert_called_once()
