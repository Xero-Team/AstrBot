"""Opt-in live compatibility tests for the real coding-agent CLIs.

Set ``ASTRBOT_LIVE_CODING_AGENTS=1`` to run them.  They make real model calls,
consume the CLI's own credentials, and are therefore excluded from the blocking
profile.  ``ASTRBOT_LIVE_CODING_AGENT_TYPES=claude_code,codex`` narrows the run
when only some CLIs are installed or authenticated.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from astrbot.core.agent.btw import coding_runner
from astrbot.core.agent.btw.coding_agents import normalize_coding_agents

pytestmark = [pytest.mark.live, pytest.mark.integration]

CASES = {
    "claude_code": "claude",
    "codex": "codex",
    "opencode": "opencode",
}


def _selected(agent_type: str) -> bool:
    selected = os.environ.get("ASTRBOT_LIVE_CODING_AGENT_TYPES", "")
    wanted = {item.strip() for item in selected.split(",") if item.strip()}
    return not wanted or agent_type in wanted


def _cli_version(executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"version unavailable: {exc}"
    output = completed.stdout.strip() or completed.stderr.strip()
    return output or f"exit {completed.returncode}"


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("ASTRBOT_LIVE_CODING_AGENTS") != "1",
    reason="set ASTRBOT_LIVE_CODING_AGENTS=1 to run real CLI tests",
)
@pytest.mark.parametrize("agent_type,command", CASES.items())
async def test_a_real_cli_creates_the_requested_file(tmp_path, agent_type, command):
    if not _selected(agent_type):
        pytest.skip("not selected by ASTRBOT_LIVE_CODING_AGENT_TYPES")
    executable = shutil.which(command)
    if executable is None:
        pytest.skip(f"{command} is not installed")
    version = _cli_version(executable)
    workspace = tmp_path / f"live-{agent_type}"
    workspace.mkdir()
    agent = normalize_coding_agents(
        [
            {
                "id": f"live-{agent_type}",
                "name": f"Live {agent_type}",
                "type": agent_type,
                "enabled": True,
                "command": executable,
                "timeout_seconds": 300,
            }
        ]
    )[0]

    result = await coding_runner.run_coding_task(
        agent,
        workspace=workspace,
        task=(
            "Create a file named live-probe.txt in the current directory whose "
            "contents are exactly `live-ok` followed by a newline. Then answer "
            "with a short completion message."
        ),
    )

    assert result.status == coding_runner.STATUS_COMPLETED, (
        f"{agent_type} {version}: {result.detail}"
    )
    assert (workspace / "live-probe.txt").read_text(
        encoding="utf-8"
    ).strip() == "live-ok"
    assert (workspace / "events.jsonl").is_file()
    assert (workspace / "run.json").is_file()
    assert result.tool_call_count >= 1, (
        f"{agent_type} {version} produced no normalized tool calls"
    )
    assert result.usage, f"{agent_type} {version} produced no usage"
    assert result.output, f"{agent_type} {version} produced no final message"
