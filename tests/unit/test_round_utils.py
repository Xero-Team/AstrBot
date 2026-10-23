from astrbot.core.agent.context.round_utils import rounds_to_text


def test_rounds_to_text_keeps_content_and_tool_calls_together():
    rounds = [
        [
            {
                "role": "assistant",
                "content": "checking",
                "tool_calls": [{"id": "call-1", "name": "search"}],
            }
        ]
    ]

    rendered = rounds_to_text(rounds)

    assert "checking" in rendered
    assert "search" in rendered
