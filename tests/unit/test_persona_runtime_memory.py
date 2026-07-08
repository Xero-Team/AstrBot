from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from astrbot.core.memory.manager import MemoryManager
from astrbot.core.memory.policy import MemoryScopePolicy
from astrbot.core.memory.tools import (
    MaintainMemoryTool,
    QueryEpisodeTool,
    SearchMemoryTool,
)
from astrbot.core.memory.writeback import MemoryFactExtractor, MemoryProfileRefresher
from astrbot.core.persona_runtime import PersonaRuntimeManager, ProactiveScheduler
from astrbot.core.persona_runtime.models import PersonaRuntimeSignal
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    _run_runtime_memory_postprocess,
)
from astrbot.core.provider.entities import ProviderRequest


def test_memory_fact_extractor_extracts_and_dedupes_core_facts():
    extractor = MemoryFactExtractor()

    facts = extractor.extract("My name is Alice. I like Rust. I like Rust.")

    assert [(fact.fact_type, fact.fact_text) for fact in facts] == [
        ("preference", "User likes Rust."),
        ("identity", "User name is Alice."),
    ]


def test_scope_policy_defaults_to_isolated():
    scope = MemoryScopePolicy().resolve("telegram:GroupMessage:g1")

    assert scope.sharing_mode == "isolated"
    assert scope.scope_id == "isolated:telegram:GroupMessage:g1"
    assert scope.allowed_chat_ids == ["telegram:GroupMessage:g1"]


@pytest.mark.asyncio
async def test_persona_runtime_state_migration_updates_frequency_and_cooldown(temp_db):
    manager = PersonaRuntimeManager(temp_db)
    await temp_db.initialize()

    state = await manager.state_store.apply_signal(
        PersonaRuntimeSignal(
            persona_id="persona-a",
            umo="telegram:FriendMessage:u1",
            user_text="are you there?",
            assistant_text="yes",
            sender_id="u1",
            mentioned=True,
            occurred_at=datetime.now(UTC),
        )
    )

    assert state.agent_state == "running"
    assert state.talk_frequency_adjust > 1.0
    assert state.consecutive_idle_count == 0
    assert state.cooldown_until is not None
    assert state.extra_state["last_mention_at"]


@pytest.mark.asyncio
async def test_persona_runtime_learns_assets_and_injects_them_as_temp_parts(temp_db):
    manager = PersonaRuntimeManager(temp_db)
    await temp_db.initialize()
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:learn",
        message_str="Can you explain `ship-it` and `ship-it`?",
        message_obj=SimpleNamespace(
            sender=SimpleNamespace(user_id="u-learn"),
            message=[],
            self_id="bot",
        ),
    )

    await manager.process_turn(
        event=event,
        persona_id="persona-learn",
        conversation_id="conv-learn",
        assistant_text="What part should I clarify?",
    )
    pending_jargon = await temp_db.list_persona_jargon_assets(
        persona_id="persona-learn",
        scope="isolated:webchat:FriendMessage:learn",
        approved=False,
    )
    await temp_db.upsert_persona_jargon_asset(
        persona_id="persona-learn",
        scope="isolated:webchat:FriendMessage:learn",
        term="ship-it",
        meaning="approve and send",
        source_message_id="manual",
        approved=True,
    )
    req = ProviderRequest(prompt="next")
    await manager.inject_context(
        req=req,
        persona_id="persona-learn",
        umo="webchat:FriendMessage:learn",
    )

    expressions = await temp_db.list_persona_expression_assets(
        persona_id="persona-learn",
        scope="isolated:webchat:FriendMessage:learn",
    )
    jargon = await temp_db.list_persona_jargon_assets(
        persona_id="persona-learn",
        scope="isolated:webchat:FriendMessage:learn",
        approved=True,
    )
    policies = await temp_db.list_persona_behavior_policies(
        persona_id="persona-learn",
        scope="isolated:webchat:FriendMessage:learn",
    )
    injected_text = "\n".join(part.text for part in req.extra_user_content_parts)

    assert [item.style_text for item in expressions] == [
        "Prefer concise direct replies in similar scenes."
    ]
    assert [item.term for item in pending_jargon] == ["ship-it"]
    assert [item.term for item in jargon] == ["ship-it"]
    assert [item.preferred_action for item in policies] == [
        "Ask one concise clarifying question before proceeding."
    ]
    assert "persona_learned_assets" in injected_text
    assert "ship-it: approve and send" in injected_text
    assert all(part._no_save for part in req.extra_user_content_parts)


@pytest.mark.asyncio
async def test_memory_writeback_profile_and_operation_log_use_real_sqlite(temp_db):
    await temp_db.initialize()
    manager = MemoryManager(temp_db)
    await manager.writeback_worker.process(
        SimpleNamespace(
            person_id="user-1",
            chat_id="telegram:FriendMessage:user-1",
            scope_id="isolated:telegram:FriendMessage:user-1",
            user_text="I like tea.",
            assistant_text="noted",
            source_message_id="conv-1:msg-1",
            evidence_message_ids=["conv-1:msg-1"],
        )
    )

    facts = await temp_db.list_memory_facts(
        person_id="user-1",
        chat_ids=["telegram:FriendMessage:user-1"],
    )
    profile = await temp_db.get_memory_profile(
        "user-1",
        "isolated:telegram:FriendMessage:user-1",
    )
    logs = await temp_db.list_memory_operation_logs(target_type="memory_fact")
    episodes = await temp_db.list_memory_episodes(
        chat_ids=["telegram:FriendMessage:user-1"],
        query="tea",
    )
    episode_logs = await temp_db.list_memory_operation_logs(
        target_type="memory_episode"
    )

    assert [fact.fact_text for fact in facts] == ["User likes tea."]
    assert profile is not None
    assert "User likes tea." in profile.profile_text
    assert len(episodes) == 1
    assert "User likes tea." in episodes[0].summary
    assert len(logs) == 1
    assert logs[0].action == "create"
    assert len(episode_logs) == 1
    assert episode_logs[0].action == "upsert"


@pytest.mark.asyncio
async def test_memory_retrieval_keeps_different_groups_isolated(temp_db):
    await temp_db.initialize()
    manager = MemoryManager(temp_db)
    await temp_db.upsert_memory_fact(
        person_id="same-user",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="User likes oranges.",
        fact_type="preference",
        source_message_id="g1:1",
    )
    await temp_db.upsert_memory_fact(
        person_id="same-user",
        chat_id="telegram:GroupMessage:g2",
        scope_id="isolated:telegram:GroupMessage:g2",
        fact_text="User likes apples.",
        fact_type="preference",
        source_message_id="g2:1",
    )

    facts = await manager.retrieval.search(
        person_id="same-user",
        chat_id="telegram:GroupMessage:g1",
        query="likes",
        limit=10,
    )
    missing = await manager.retrieval.search(
        person_id="same-user",
        chat_id="telegram:GroupMessage:g1",
        query="bananas",
        limit=10,
    )

    assert [fact.fact_text for fact in facts] == ["User likes oranges."]
    assert missing == []


@pytest.mark.asyncio
async def test_memory_retrieval_uses_explicit_scope_policy_for_shared_recall(temp_db):
    await temp_db.initialize()
    manager = MemoryManager(temp_db)
    await temp_db.upsert_memory_fact(
        person_id="same-user",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="User likes oranges.",
        fact_type="preference",
        source_message_id="g1:1",
    )
    await temp_db.upsert_memory_fact(
        person_id="same-user",
        chat_id="telegram:GroupMessage:g2",
        scope_id="isolated:telegram:GroupMessage:g2",
        fact_text="User likes apples.",
        fact_type="preference",
        source_message_id="g2:1",
    )
    await temp_db.upsert_memory_scope_policy(
        owner_scope_id="isolated:telegram:GroupMessage:g1",
        target_scope_id="isolated:telegram:GroupMessage:g2",
    )

    facts = await manager.retrieval.search(
        person_id="same-user",
        chat_id="telegram:GroupMessage:g1",
        query="apples",
        limit=10,
    )

    assert [fact.fact_text for fact in facts][:1] == ["User likes apples."]


@pytest.mark.asyncio
async def test_profile_refresher_updates_existing_profile_version(temp_db):
    await temp_db.initialize()
    refresher = MemoryProfileRefresher(temp_db)
    await temp_db.upsert_memory_fact(
        person_id="user-2",
        chat_id="webchat:FriendMessage:user-2",
        scope_id="isolated:webchat:FriendMessage:user-2",
        fact_text="User likes SQLite.",
        fact_type="preference",
        source_message_id="msg-1",
    )

    first = await refresher.refresh(
        person_id="user-2",
        chat_scope="isolated:webchat:FriendMessage:user-2",
    )
    second = await refresher.refresh(
        person_id="user-2",
        chat_scope="isolated:webchat:FriendMessage:user-2",
    )
    profile = await temp_db.get_memory_profile(
        "user-2",
        "isolated:webchat:FriendMessage:user-2",
        include_override=False,
    )

    assert first == second
    assert profile is not None
    assert profile.source_version == 2


def test_proactive_scheduler_respects_disabled_and_cooldown():
    scheduler = ProactiveScheduler()
    state = SimpleNamespace(
        extra_state={"proactive_enabled": False},
        cooldown_until=None,
        agent_state="running",
        talk_frequency_adjust=1.2,
    )

    assert scheduler.evaluate(state, unread_count=3).reason == "proactive_disabled"

    state.extra_state["proactive_enabled"] = True
    state.cooldown_until = datetime.now(UTC) + timedelta(minutes=1)

    assert scheduler.evaluate(state, unread_count=3).reason == "cooldown"


@pytest.mark.asyncio
async def test_post_turn_runtime_memory_smoke_uses_real_sqlite(temp_db):
    await temp_db.initialize()
    persona_runtime = PersonaRuntimeManager(temp_db)
    memory_manager = MemoryManager(temp_db)
    await memory_manager.initialize()
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:session-smoke",
        message_str="I like deterministic tests.",
        message_obj=SimpleNamespace(
            sender=SimpleNamespace(user_id="user-smoke"),
            message=[],
            self_id="bot",
        ),
        get_extra=lambda key: "persona-smoke" if key == "selected_persona_id" else None,
    )

    try:
        await _run_runtime_memory_postprocess(
            event=event,
            req=ProviderRequest(conversation=SimpleNamespace(cid="conv-smoke")),
            assistant_text="noted",
            persona_runtime_manager=persona_runtime,
            memory_manager=memory_manager,
        )
        await memory_manager.writeback_worker.queue.join()
    finally:
        await memory_manager.terminate()

    state = await temp_db.get_persona_session_state(
        "persona-smoke",
        "webchat:FriendMessage:session-smoke",
    )
    facts = await temp_db.list_memory_facts(
        person_id="user-smoke",
        chat_ids=["webchat:FriendMessage:session-smoke"],
    )
    profile = await temp_db.get_memory_profile(
        "user-smoke",
        "isolated:webchat:FriendMessage:session-smoke",
    )
    episodes = await temp_db.list_memory_episodes(
        chat_ids=["webchat:FriendMessage:session-smoke"],
        query="deterministic",
    )

    assert state is not None
    assert state.agent_state == "running"
    assert [fact.fact_text for fact in facts] == ["User likes deterministic tests."]
    assert profile is not None
    assert "deterministic tests" in profile.profile_text
    assert len(episodes) == 1
    assert "deterministic tests" in episodes[0].summary


@pytest.mark.asyncio
async def test_maintain_memory_tool_is_scoped_and_audited(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    fact, _ = await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="User likes scoped deletion.",
        fact_type="preference",
        source_message_id="g1:1",
    )
    await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g2",
        scope_id="isolated:telegram:GroupMessage:g2",
        fact_text="User likes hidden facts.",
        fact_type="preference",
        source_message_id="g2:1",
    )
    event = SimpleNamespace(
        unified_msg_origin="telegram:GroupMessage:g1",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="user-tool")),
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(memory_manager=memory_manager),
            event=event,
        )
    )
    tool = MaintainMemoryTool()

    preview = await tool.call(context, action="preview", query="scoped", limit=5)
    result = await tool.call(context, fact_id=fact.id, action="delete")
    blocked = await tool.call(context, fact_id=fact.id + 1, action="delete")
    restore = await tool.call(context, fact_id=fact.id, action="restore")
    logs = await temp_db.list_memory_operation_logs(target_id=str(fact.id))

    assert f"[fact_id={fact.id} status=active confidence=0.60]" in preview
    assert "hidden facts" not in preview
    assert result == f"Memory fact {fact.id} deleted."
    assert restore == f"Memory fact {fact.id} restored."
    assert blocked == "Memory fact is outside the current user's isolated memory scope."
    assert [log.action for log in logs[:2]] == ["restore", "delete"]


@pytest.mark.asyncio
async def test_search_memory_returns_fact_id_for_maintenance_flow(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    fact, _ = await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="用户喜欢猫娘。",
        fact_type="preference",
        source_message_id="g1:catgirl",
    )
    event = SimpleNamespace(
        unified_msg_origin="telegram:GroupMessage:g1",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="user-tool")),
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(memory_manager=memory_manager),
            event=event,
        )
    )

    search_result = await SearchMemoryTool().call(context, query="猫娘", limit=3)
    delete_result = await MaintainMemoryTool().call(
        context,
        fact_id=fact.id,
        action="delete",
        reason="user requested deletion",
    )
    after_delete = await SearchMemoryTool().call(context, query="猫娘", limit=3)
    logs = await temp_db.list_memory_operation_logs(target_id=str(fact.id))

    assert f"[fact_id={fact.id} status=active confidence=0.60]" in search_result
    assert delete_result == f"Memory fact {fact.id} deleted."
    assert after_delete == "No matching memory found."
    assert logs[0].action == "delete"
    assert logs[0].reason == "user requested deletion"


@pytest.mark.asyncio
async def test_maintain_memory_preview_does_not_bulk_delete_across_groups(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    first, _ = await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="用户喜欢猫娘。",
        fact_type="preference",
        source_message_id="g1:catgirl",
    )
    second, _ = await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="用户喜欢猫娘咖啡馆。",
        fact_type="preference",
        source_message_id="g1:catgirl-cafe",
    )
    hidden, _ = await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g2",
        scope_id="isolated:telegram:GroupMessage:g2",
        fact_text="用户喜欢猫娘周边。",
        fact_type="preference",
        source_message_id="g2:catgirl",
    )
    event = SimpleNamespace(
        unified_msg_origin="telegram:GroupMessage:g1",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="user-tool")),
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(memory_manager=memory_manager),
            event=event,
        )
    )

    preview = await MaintainMemoryTool().call(
        context,
        action="preview",
        target_text="猫娘",
        limit=10,
    )
    logs_before = await temp_db.list_memory_operation_logs(target_type="memory_fact")
    delete_first = await MaintainMemoryTool().call(
        context,
        action="delete",
        fact_id=first.id,
        reason="confirmed single fact",
    )

    assert f"fact_id={first.id}" in preview
    assert f"fact_id={second.id}" in preview
    assert f"fact_id={hidden.id}" not in preview
    assert logs_before == []
    assert delete_first == f"Memory fact {first.id} deleted."
    assert (await temp_db.get_memory_fact(second.id)).status == "active"
    assert (await temp_db.get_memory_fact(hidden.id)).status == "active"


@pytest.mark.asyncio
async def test_maintain_memory_does_not_maintain_shared_scope_facts(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    local, _ = await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="用户喜欢本群猫娘话题。",
        fact_type="preference",
        source_message_id="g1:catgirl",
    )
    shared, _ = await temp_db.upsert_memory_fact(
        person_id="user-tool",
        chat_id="telegram:GroupMessage:g2",
        scope_id="isolated:telegram:GroupMessage:g2",
        fact_text="用户喜欢共享群猫娘话题。",
        fact_type="preference",
        source_message_id="g2:catgirl",
    )
    await temp_db.upsert_memory_scope_policy(
        owner_scope_id="isolated:telegram:GroupMessage:g1",
        target_scope_id="isolated:telegram:GroupMessage:g2",
    )
    event = SimpleNamespace(
        unified_msg_origin="telegram:GroupMessage:g1",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="user-tool")),
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(memory_manager=memory_manager),
            event=event,
        )
    )

    search_result = await SearchMemoryTool().call(context, query="共享群", limit=5)
    preview = await MaintainMemoryTool().call(
        context,
        action="preview",
        target_text="猫娘",
        limit=10,
    )
    delete_shared = await MaintainMemoryTool().call(
        context,
        action="delete",
        fact_id=shared.id,
        reason="must not cross maintain scope",
    )

    assert f"fact_id={shared.id}" in search_result
    assert f"fact_id={local.id}" in preview
    assert f"fact_id={shared.id}" not in preview
    assert delete_shared == (
        "Memory fact is outside the current user's isolated memory scope."
    )
    assert (await temp_db.get_memory_fact(shared.id)).status == "active"


@pytest.mark.asyncio
async def test_query_episode_tool_uses_current_scope(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    await temp_db.upsert_memory_episode(
        episode_id="episode-tool",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        title="Migration planning",
        summary="User and assistant discussed runtime memory migration.",
        participant_ids=["user-tool"],
        source_message_ids=["g1:episode"],
    )
    await temp_db.upsert_memory_episode(
        episode_id="episode-hidden",
        chat_id="telegram:GroupMessage:g2",
        scope_id="isolated:telegram:GroupMessage:g2",
        title="Hidden planning",
        summary="This should remain outside the current isolated scope.",
        participant_ids=["user-tool"],
        source_message_ids=["g2:episode"],
    )
    event = SimpleNamespace(
        unified_msg_origin="telegram:GroupMessage:g1",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="user-tool")),
    )
    context = SimpleNamespace(
        context=SimpleNamespace(
            context=SimpleNamespace(memory_manager=memory_manager),
            event=event,
        )
    )

    result = await QueryEpisodeTool().call(context, query="planning", limit=5)
    missing = await QueryEpisodeTool().call(context, query="not-present", limit=5)

    assert "Migration planning" in result
    assert "Hidden planning" not in result
    assert missing == "No matching episode found."


@pytest.mark.asyncio
async def test_memory_injection_does_not_include_unmatched_episode(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    event = SimpleNamespace(
        unified_msg_origin="telegram:GroupMessage:g1",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="user-episode")),
    )
    await temp_db.upsert_memory_episode(
        episode_id="episode-unrelated",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        title="Database migration",
        summary="User and assistant discussed SQLite schema changes.",
        participant_ids=["user-episode"],
        source_message_ids=["g1:episode"],
    )
    req = ProviderRequest(prompt="Tell me about bananas")

    await memory_manager.inject_context(req=req, event=event, query="bananas")

    assert req.extra_user_content_parts == []


@pytest.mark.asyncio
async def test_episode_retrieval_matches_partial_query_terms(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    event = SimpleNamespace(
        unified_msg_origin="telegram:GroupMessage:g1",
        message_obj=SimpleNamespace(sender=SimpleNamespace(user_id="user-episode")),
    )
    await temp_db.upsert_memory_episode(
        episode_id="episode-partial",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        title="Runtime migration planning",
        summary="User and assistant discussed runtime memory migration.",
        participant_ids=["user-episode"],
        source_message_ids=["g1:episode"],
    )
    req = ProviderRequest(prompt="runtime bananas")

    episodes = await memory_manager.retrieval.search_episodes(
        chat_id="telegram:GroupMessage:g1",
        query="runtime bananas",
        limit=3,
    )
    await memory_manager.inject_context(
        req=req,
        event=event,
        query="runtime bananas",
    )

    assert [episode.title for episode in episodes] == ["Runtime migration planning"]
    assert "Runtime migration planning" in req.extra_user_content_parts[0].text


@pytest.mark.asyncio
async def test_memory_tuning_probe_records_real_retrieval_metrics(temp_db):
    await temp_db.initialize()
    memory_manager = MemoryManager(temp_db)
    await temp_db.upsert_memory_fact(
        person_id="user-tune",
        chat_id="telegram:GroupMessage:g1",
        scope_id="isolated:telegram:GroupMessage:g1",
        fact_text="User likes retrieval probes.",
        fact_type="preference",
        source_message_id="g1:tune",
    )

    task = await memory_manager.tuning.run_retrieval_probe(
        person_id="user-tune",
        chat_id="telegram:GroupMessage:g1",
        queries=["retrieval probes", "missing topic"],
        limit=2,
    )

    assert task.status == "completed"
    assert task.target_scope == "isolated:telegram:GroupMessage:g1"
    assert task.evaluation_result["query_count"] == 2
    assert task.evaluation_result["queries_with_results"] == 1
    assert task.evaluation_result["coverage"] == 0.5
    assert task.evaluation_result["samples"][0]["top_fact"] == (
        "User likes retrieval probes."
    )
    assert task.evaluation_result["samples"][1]["top_fact"] is None
