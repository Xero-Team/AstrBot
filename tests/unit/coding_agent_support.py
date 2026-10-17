"""Shared cases for the BTW coding-agent stream contract tests."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from astrbot.core.agent.btw import coding_agents

FIXTURES = Path(__file__).parents[1] / "fixtures" / "coding_agents"
FAKE_CLI = FIXTURES / "fake_cli.py"


@dataclass(frozen=True, slots=True)
class CodingAgentCase:
    """One CLI whose stream contract is exercised by the shared tests."""

    agent_type: str
    fixture: Path
    stream_final_text: str
    result_final_text: str


CASES = (
    CodingAgentCase(
        agent_type="claude_code",
        fixture=FIXTURES / "claude_code" / "basic.ndjson",
        stream_final_text="claude final",
        result_final_text="claude final",
    ),
    CodingAgentCase(
        agent_type="codex",
        fixture=FIXTURES / "codex" / "basic.ndjson",
        stream_final_text="codex final",
        result_final_text="fixture final",
    ),
    CodingAgentCase(
        agent_type="opencode",
        fixture=FIXTURES / "opencode" / "basic.ndjson",
        stream_final_text="opencode final",
        result_final_text="opencode final",
    ),
)


def agent_entry(case: CodingAgentCase, **overrides) -> dict:
    """Return a raw profile entry that launches the fake CLI for one case."""
    entry = {
        "id": case.agent_type,
        "name": case.agent_type,
        "type": case.agent_type,
        "enabled": True,
        "command": sys.executable,
        "extra_args": [str(FAKE_CLI), str(case.fixture)],
        "timeout_seconds": 30,
    }
    entry.update(overrides)
    return entry


def normalized_agent(case: CodingAgentCase, **overrides) -> dict:
    """Return the backend's normalized form of one fake agent."""
    return coding_agents.normalize_coding_agents([agent_entry(case, **overrides)])[0]
