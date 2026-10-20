"""One response-to-event conversion shared by every agent step path."""

from astrbot.core.agent.llm_types import LLMCitation, LLMResponse, LLMSource
from astrbot.core.agent.response_events import (
    final_response_events,
    streaming_response_events,
)
from astrbot.core.message.message_event_result import MessageChain


def test_streaming_events_keep_reasoning_and_text_separate():
    response = LLMResponse(
        role="assistant",
        reasoning_content="thinking",
        completion_text="answer",
    )

    events = streaming_response_events(response)

    assert [event.type for event in events] == ["streaming_delta", "streaming_delta"]
    assert events[0].data["chain"].type == "reasoning"
    assert events[0].data["chain"].get_plain_text() == "thinking"
    assert events[1].data["chain"].get_plain_text() == "answer"


def test_streaming_events_prefer_the_result_chain_over_plain_text():
    chain = MessageChain().message("chain result")
    response = LLMResponse(
        role="assistant",
        completion_text="plain result",
        result_chain=chain,
    )

    events = streaming_response_events(response)

    assert len(events) == 1
    assert events[0].data["chain"] is chain


def test_final_events_include_sources_before_the_text_result():
    chain = MessageChain().message("answer")
    response = LLMResponse(
        role="assistant",
        completion_text="ignored",
        result_chain=chain,
        citations=[LLMCitation(url="https://example.com/citation")],
        sources=[LLMSource(url="https://example.com/source", title="source")],
    )

    events = final_response_events(response)

    assert [event.type for event in events] == ["llm_sources", "llm_result"]
    sources = events[0].data["chain"].chain[0].data
    assert sources["citations"] == [
        {
            "url": "https://example.com/citation",
            "title": None,
            "start_index": None,
            "end_index": None,
        }
    ]
    assert sources["sources"] == [
        {
            "url": "https://example.com/source",
            "title": "source",
            "snippet": None,
            "source_type": None,
        }
    ]
    assert events[1].data["chain"] is chain


def test_final_events_split_reasoning_from_the_answer():
    response = LLMResponse(
        role="assistant",
        reasoning_content="thinking",
        completion_text="answer",
    )

    events = final_response_events(response)

    assert [event.type for event in events] == ["llm_result", "llm_result"]
    assert events[0].data["chain"].type == "reasoning"
    assert events[1].data["chain"].get_plain_text() == "answer"
