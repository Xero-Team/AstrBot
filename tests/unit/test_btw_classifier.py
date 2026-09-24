"""Offline contracts for capability-aware classifier routing and safe fallbacks."""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.core.astr_main_agent as main_agent
from astrbot.core.agent.btw.classifier import (
    ROUTING_QUESTION,
    classify_request,
    routing_state,
)
from astrbot.core.agent.btw.submission import submit_work_task
from astrbot.core.agent.conversation_loop import ConversationLoop
from astrbot.core.agent.llm_types import LLMResponse, TokenUsage
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.message.components import Image, Plain
from astrbot.core.provider.provider import ClassifierProvider, Provider
from astrbot.core.skills._skill_inventory import SkillInfo
from astrbot.core.tools.function_tool_manager import FunctionToolManager
from astrbot.core.typed_decision import ClassifierResult

CAPABILITIES = {
    "conversation": [],
    "work": [{"name": "tool:query", "summary": "Query weather"}],
}


def classifier_response(decision="work", confidence=0.99):
    return ClassifierResult.model_validate(
        {
            "model": "jev-test",
            "answers": {
                "route": {
                    "type": "choice",
                    "choice": decision,
                    "confidence": confidence,
                    "probabilities": {
                        key: 1.0 if key == decision else 0.0
                        for key in ROUTING_QUESTION.criteria
                    },
                }
            },
            "usage": {"input_tokens": 12, "output_tokens": 8},
        }
    )


def providers(decision="work", confidence=0.99):
    classifier = MagicMock(spec=ClassifierProvider)
    classifier.get_model.return_value = "jev-test"
    classifier.evaluate = AsyncMock(
        return_value=classifier_response(decision, confidence)
    )
    fallback = MagicMock(spec=Provider)
    fallback.provider_config = {}
    fallback.get_model.return_value = "chat-test"
    fallback.text_chat = AsyncMock(
        return_value=LLMResponse(
            role="assistant",
            completion_text='{"decision":"conversation","confidence":0.99}',
            usage=TokenUsage(input_other=10, output=5),
        )
    )
    return classifier, fallback


class Event:
    def __init__(self, text="Query the weather"):
        self.message_str = text
        self.message_obj = SimpleNamespace(message=[Plain(text)])
        self.unified_msg_origin = "webchat:FriendMessage:test"
        self._extras = {}
        self._stopped = False
        self.result = None
        self.plugins_name = None
        self.platform_meta = SimpleNamespace(support_proactive_message=False)
        self.auth_context = SimpleNamespace(
            source="im", authenticated=False, metadata={}
        )
        self.subject = SimpleNamespace(kind="platform")

    def set_extra(self, key, value):
        self._extras[key] = value

    def get_extra(self, key, default=None):
        return self._extras.get(key, default)

    def is_stopped(self):
        return self._stopped

    def set_result(self, value):
        self.result = value

    def get_platform_name(self):
        return "webchat"

    def get_message_type(self):
        return None


class Executor:
    def __init__(self):
        self.initialize = AsyncMock()
        self.session_services = SimpleNamespace(
            should_process_llm_request=AsyncMock(return_value=True)
        )
        self.calls = []

    async def process(self, event):
        self.calls.append(event.get_extra("btw_loop"))
        yield


@pytest.fixture
def profile():
    return {
        "btw": {
            "enabled": True,
            "work_loop": {"enabled": True},
            "classifier": {
                "enabled": True,
                "provider_id": "jev",
                "confidence_threshold": 0.85,
            },
        },
        "agent_runner": {"runner_type": "local"},
        "provider_settings": {"enable": True},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["absent", "error", "timeout", "low"])
async def test_fallback_uses_same_state_and_strict_tool_free_decision(failure):
    classifier, fallback = providers(confidence=0.5 if failure == "low" else 0.99)
    if failure in ("error", "timeout"):
        classifier.evaluate.side_effect = (
            TimeoutError() if failure == "timeout" else RuntimeError("secret")
        )
    state = routing_state("Query weather", CAPABILITIES)
    result = await classify_request(
        state, None if failure == "absent" else classifier, fallback
    )
    assert (result.decision, result.source) == ("conversation", "llm")
    kwargs = fallback.text_chat.call_args.kwargs
    assert json.loads(kwargs["prompt"]) == state
    assert "func_tool" not in kwargs and "contexts" not in kwargs
    assert kwargs["request_max_retries"] == 1
    assert result.attempts[-1]["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert "secret" not in json.dumps(result.attempts)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        '{"decision":"work","confidence":0.2}',
        '{"decision":"work","confidence":true}',
        '```json\n{"decision":"work","confidence":1}\n```',
        '{"decision":"work","confidence":1,"tool":"exec"}',
        "not json",
    ],
)
async def test_invalid_or_uncertain_fallback_never_launches_work(text):
    _, fallback = providers()
    fallback.text_chat.return_value = LLMResponse(
        role="assistant", completion_text=text
    )
    result = await classify_request(
        routing_state("do work", CAPABILITIES), None, fallback
    )
    assert (result.decision, result.source) == ("conversation", "safe_default")


@pytest.mark.asyncio
async def test_fallback_errors_tool_calls_and_cancel_are_not_execution():
    _, fallback = providers()
    fallback.text_chat.side_effect = RuntimeError("token=secret")
    state = routing_state("do work", CAPABILITIES)
    assert (await classify_request(state, None, fallback)).source == "safe_default"
    fallback.text_chat.side_effect = None
    fallback.text_chat.return_value = LLMResponse(
        role="assistant",
        completion_text='{"decision":"work","confidence":1}',
        tools_call_name=["exec"],
    )
    assert (await classify_request(state, None, fallback)).source == "safe_default"
    fallback.text_chat.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await classify_request(state, None, fallback)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["conversation", "work", "clarify", "unavailable"])
async def test_high_confidence_decision_skips_fallback(decision):
    classifier, fallback = providers(decision)
    result = await classify_request(
        routing_state("request", CAPABILITIES), classifier, fallback
    )
    assert result.decision == decision
    fallback.text_chat.assert_not_awaited()
    assert result.attempts[0]["model"] == "jev-test"


@pytest.mark.asyncio
async def test_work_without_any_exclusive_capability_is_unavailable():
    classifier, fallback = providers()
    state = routing_state(
        "request", {"conversation": CAPABILITIES["work"], "work": CAPABILITIES["work"]}
    )
    assert (
        await classify_request(state, classifier, fallback)
    ).decision == "unavailable"


def test_payload_allowlist_redacts_both_message_and_capability_text():
    secret = "api_key=abc123 Bearer hidden /Users/name/private C:\\secret\\file ./local/file repo/file.py https://example.com?q=private sk-short-secret"
    caps = {
        loop: [{"name": "tool:query", "summary": secret, "schema": {"key": "leak"}}]
        for loop in ("conversation", "work")
    }
    state = routing_state(secret, caps)
    encoded = json.dumps(state)
    for text in (
        "abc123",
        "hidden",
        "private",
        "secret",
        "local/file",
        "repo/file",
        "example.com",
        "schema",
        "leak",
    ):
        assert text not in encoded
    assert set(state) == {"message", "capabilities"}
    assert set(state["capabilities"]["work"][0]) == {"name", "summary"}


async def initialized_loop(profile, monkeypatch, decision="work"):
    classifier, fallback = providers(decision)
    context = SimpleNamespace(
        get_provider_by_id=lambda name: classifier if name == "jev" else fallback,
        get_using_provider=lambda **_: fallback,
    )
    executor = Executor()
    loop = ConversationLoop(executor)
    await loop.initialize(
        SimpleNamespace(astrbot_config=profile, execution_context=context)
    )
    monkeypatch.setattr(
        main_agent,
        "resolve_btw_capabilities",
        AsyncMock(return_value=deepcopy(CAPABILITIES)),
    )
    return loop, executor, classifier, fallback


@pytest.mark.asyncio
async def test_work_handoff_once_and_identity_unchanged(profile, monkeypatch):
    loop, executor, classifier, _ = await initialized_loop(profile, monkeypatch)
    event = Event()
    auth, subject = event.auth_context, event.subject
    await asyncio.gather(*[consume(loop.process(event)) for _ in range(2)])
    assert executor.calls == ["work"]
    classifier.evaluate.assert_awaited_once()
    assert event.auth_context is auth and event.subject is subject
    assert event.auth_context.metadata == {}
    assert event.get_extra("btw_work_session_id")
    assert [item async for item in loop.process(event)] == []


async def consume(stream):
    return [item async for item in stream]


@pytest.mark.asyncio
async def test_concurrent_reentry_during_admission_cannot_duplicate_work(
    profile, monkeypatch
):
    loop, executor, classifier, _ = await initialized_loop(profile, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def admission(_event):
        entered.set()
        await release.wait()
        return True

    executor.session_services.should_process_llm_request.side_effect = admission
    event = Event()
    first = asyncio.create_task(consume(loop.process(event)))
    await entered.wait()
    assert await consume(loop.process(event)) == []
    release.set()
    await first
    assert executor.calls == ["work"]
    classifier.evaluate.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["cancel", "stop", "disable"])
async def test_inflight_decision_cannot_start_withdrawn_work(
    profile, monkeypatch, interruption
):
    loop, executor, classifier, _ = await initialized_loop(profile, monkeypatch)
    event = Event()

    async def interrupted(*_args):
        if interruption == "cancel":
            raise asyncio.CancelledError()
        if interruption == "stop":
            event._stopped = True
        else:
            profile["btw"]["work_loop"]["enabled"] = False
        return classifier_response()

    classifier.evaluate.side_effect = interrupted
    if interruption == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await consume(loop.process(event))
    else:
        await consume(loop.process(event))
    assert "work" not in executor.calls


@pytest.mark.asyncio
async def test_runtime_fallback_selection_uses_configured_chat_model(
    profile, monkeypatch
):
    profile["btw"]["classifier"].update(
        provider_id="missing", fallback_provider_id="chat"
    )
    loop, executor, _, fallback = await initialized_loop(profile, monkeypatch)
    event = Event()
    await consume(loop.process(event))
    fallback.text_chat.assert_awaited_once()
    assert executor.calls == ["conversation"]
    assert event.get_extra("btw_classifier_result")["source"] == "llm"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "disabled",
    [
        "btw",
        "work",
        "classifier",
        "empty",
        "session",
        "ai",
        "third_party",
        "attachment",
        "explicit",
    ],
)
async def test_disabled_or_unsupported_paths_do_not_classify(
    profile, monkeypatch, disabled
):
    if disabled in ("btw", "work", "classifier"):
        target = (
            profile["btw"]
            if disabled == "btw"
            else profile["btw"]["work_loop" if disabled == "work" else "classifier"]
        )
        target["enabled"] = False
    if disabled == "empty":
        profile["btw"]["classifier"]["provider_id"] = ""
    if disabled == "third_party":
        profile["agent_runner"]["runner_type"] = "dify"
    if disabled == "ai":
        profile["provider_settings"]["enable"] = False
    loop, executor, classifier, fallback = await initialized_loop(profile, monkeypatch)
    event = Event()
    if disabled == "session":
        executor.session_services.should_process_llm_request.return_value = False
    if disabled == "attachment":
        event.message_obj.message.append(Image(file="file:///private/file.png"))
    if disabled == "explicit":
        event.set_extra("btw_force_work", True)
    await consume(loop.process(event))
    classifier.evaluate.assert_not_awaited()
    fallback.text_chat.assert_not_awaited()
    assert executor.calls == (
        []
        if disabled == "session"
        else [
            "work"
            if disabled == "explicit"
            else "conversation"
            if disabled != "btw"
            else None
        ]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["clarify", "unavailable", "conversation"])
@pytest.mark.parametrize("clarify", [False, True])
async def test_non_work_decision_never_allows_secondary_handoff(
    profile, monkeypatch, decision, clarify
):
    profile["btw"]["classifier"]["clarify_on_uncertain"] = clarify
    loop, executor, _, _ = await initialized_loop(profile, monkeypatch, decision)
    event = Event()
    await consume(loop.process(event))
    assert "work" not in executor.calls
    assert event.get_extra("btw_classifier_no_handoff")
    assert await submit_work_task(SimpleNamespace(), event, "start work anyway") is None
    if decision == "unavailable" or (decision == "clarify" and clarify):
        assert event.result is not None and not executor.calls
    else:
        assert executor.calls == ["conversation"]


@pytest.mark.asyncio
@pytest.mark.parametrize("threshold", [-1, 2, float("nan"), "0.9", True])
async def test_invalid_threshold_keeps_conversation_without_external_calls(
    profile, monkeypatch, threshold
):
    profile["btw"]["classifier"]["confidence_threshold"] = threshold
    loop, executor, classifier, fallback = await initialized_loop(profile, monkeypatch)
    await consume(loop.process(Event()))
    assert executor.calls == ["conversation"]
    classifier.evaluate.assert_not_awaited()
    fallback.text_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_capability_resolver_matches_live_catalog_and_keeps_request_inert(
    tmp_path, profile
):
    profile["provider_settings"]["proactive_capability"] = {"add_cron_tools": False}
    path = tmp_path / "SKILL.md"
    path.write_text(
        "---\nname: weather\ndescription: Read weather\n---\n# Weather",
        encoding="utf-8",
    )
    skill = SkillInfo(
        name="weather",
        description="Read weather",
        path=str(path),
        host_path=str(path),
        active=True,
    )
    plugin = SimpleNamespace(
        name="weather", activated=True, reserved=False, root_dir_name="weather"
    )
    query = FunctionTool(
        name="query",
        description="Query weather",
        parameters={"secret_schema": "never sent"},
        handler_module_path="weather.main",
        required_actions=("session.read",),
    )
    tools = FunctionToolManager()
    tools.func_list = [query]
    context = SimpleNamespace(
        catalogs=SimpleNamespace(
            plugins=SimpleNamespace(
                all=lambda: [plugin], get_by_module=lambda _: plugin
            )
        ),
        get_config=lambda **_: profile,
        get_llm_tool_manager=lambda: tools,
        subagent_orchestrator=None,
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value=None),
            get_conversation=AsyncMock(),
        ),
        persona_manager=SimpleNamespace(
            resolve_selected_persona=AsyncMock(return_value=(None, None, None, False))
        ),
        skill_manager=SimpleNamespace(
            list_skills=lambda **_: [skill],
            list_workspace_skills=MagicMock(return_value=[]),
        ),
    )
    event = Event()
    event.set_extra("keep", object())
    original = dict(event._extras)
    profile["btw"]["skill_routes"] = [{"skill_name": "weather", "loop": "work"}]
    caps = await main_agent.resolve_btw_capabilities(event, context)
    assert caps["conversation"] == []
    assert {item["name"] for item in caps["work"]} == {
        "tool:query",
        "tool:read_skill",
        "skill:weather",
    }
    assert "secret_schema" not in json.dumps(caps)
    assert event._extras == original
    context.conversation_manager.get_conversation.assert_not_awaited()
    context.skill_manager.list_workspace_skills.assert_not_called()
    profile["btw"]["plugin_routes"] = [{"plugin_id": "weather", "loop": "both"}]
    caps = await main_agent.resolve_btw_capabilities(event, context)
    assert {item["name"] for item in caps["conversation"]} == {"tool:query"}
    skill.source_type = "plugin"
    skill.plugin_name = "weather"
    profile["plugin_set"] = []
    hidden = await main_agent.resolve_btw_capabilities(event, context)
    assert not any(
        item["name"].startswith("skill:") for items in hidden.values() for item in items
    )
    context.persona_manager.resolve_selected_persona.return_value = (
        "restricted",
        {"tools": [], "skills": []},
        None,
        False,
    )
    assert await main_agent.resolve_btw_capabilities(event, context) == {
        "conversation": [],
        "work": [],
    }
