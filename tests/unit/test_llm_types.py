from astrbot.core.agent.llm_types import LLMResponse
from astrbot.core.message.message_event_result import MessageChain


def test_llm_response_preserves_chain_text_when_completion_is_omitted() -> None:
    chain = MessageChain().message("text from chain")

    response = LLMResponse(role="assistant", result_chain=chain)

    assert response.completion_text == "text from chain"


def test_llm_response_applies_explicit_text_to_provided_chain() -> None:
    chain = MessageChain().message("stale text")

    response = LLMResponse(
        role="assistant",
        completion_text="replacement text",
        result_chain=chain,
    )

    assert response.completion_text == "replacement text"
