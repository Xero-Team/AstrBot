"""Translate one LLM response into the agent's transport events."""

from astrbot.core.agent.llm_types import LLMResponse
from astrbot.core.agent.response import AgentResponse, AgentResponseData
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import MessageChain


def streaming_response_events(response: LLMResponse) -> list[AgentResponse]:
    """Translate a provider stream chunk into agent output events."""
    events: list[AgentResponse] = []
    if response.reasoning_content:
        events.append(
            AgentResponse(
                type="streaming_delta",
                data=AgentResponseData(
                    chain=MessageChain(type="reasoning").message(
                        response.reasoning_content,
                    ),
                ),
            )
        )
    if response.result_chain:
        events.append(
            AgentResponse(
                type="streaming_delta",
                data=AgentResponseData(chain=response.result_chain),
            )
        )
    elif response.completion_text:
        events.append(
            AgentResponse(
                type="streaming_delta",
                data=AgentResponseData(
                    chain=MessageChain().message(response.completion_text),
                ),
            )
        )
    return events


def final_response_events(response: LLMResponse) -> list[AgentResponse]:
    """Build source, reasoning, and final-content events for one response."""
    events: list[AgentResponse] = []
    if response.citations or response.sources:
        events.append(
            AgentResponse(
                type="llm_sources",
                data=AgentResponseData(
                    chain=MessageChain(
                        type="llm_sources",
                        chain=[
                            Json(
                                data={
                                    "citations": [
                                        citation.__dict__
                                        for citation in response.citations
                                    ],
                                    "sources": [
                                        source.__dict__ for source in response.sources
                                    ],
                                }
                            )
                        ],
                    )
                ),
            )
        )
    if response.reasoning_content:
        events.append(
            AgentResponse(
                type="llm_result",
                data=AgentResponseData(
                    chain=MessageChain(type="reasoning").message(
                        response.reasoning_content,
                    ),
                ),
            )
        )
    if response.result_chain:
        events.append(
            AgentResponse(
                type="llm_result",
                data=AgentResponseData(chain=response.result_chain),
            )
        )
    elif response.completion_text:
        events.append(
            AgentResponse(
                type="llm_result",
                data=AgentResponseData(
                    chain=MessageChain().message(response.completion_text),
                ),
            )
        )
    return events
