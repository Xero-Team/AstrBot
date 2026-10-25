from astrbot.core.agent.runners.dify.dify_agent_runner import _workflow_inputs


def test_fixed_workflow_fields_override_session_variables():
    inputs = _workflow_inputs(
        "query",
        "actual prompt",
        "session-1",
        {
            "query": "forged prompt",
            "astrbot_session_id": "other-session",
            "variable": "value",
        },
    )

    assert inputs == {
        "variable": "value",
        "query": "actual prompt",
        "astrbot_session_id": "session-1",
    }
