"""Tests for running a coding agent inside its own task folder."""

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from astrbot.core.agent.btw import coding_agents as ca
from astrbot.core.agent.btw import coding_runner as cr
from astrbot.core.utils.process_tree import ProcessTree

WRITE_AND_ECHO = (
    "import pathlib, sys;"
    "data = sys.stdin.read();"
    "pathlib.Path('out.txt').write_text(data, encoding='utf-8');"
    "print('done')"
)
SLEEP_FOREVER = "import time; time.sleep(30)"
# How long a helper outlives the launcher that started it.
HELPER_SLEEP_SECONDS = 4.0
# A helper that writes only if it survives, the shape of a coding agent CLI
# leaving a ``node`` process behind.
HELPER = (
    "import time,pathlib;"
    f"time.sleep({HELPER_SLEEP_SECONDS});"
    "pathlib.Path('sentinel.txt').write_text('x')"
)
# A launcher that hands the work to a helper and exits at once.  It hands the
# helper no console of its own, the way a CLI does when it leaves a daemon
# behind, so nothing but the tree keeps the helper reachable.
DETACHED_HELPER = (
    "import subprocess, sys;"
    "subprocess.Popen("
    f"[sys.executable, '-c', {HELPER!r}],"
    "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,"
    "stderr=subprocess.DEVNULL);"
    "print('spawned')"
)
# The same launcher with the helper on its own handles.  This is also the shape
# of the interpreter shim a virtual environment installs on Windows: the shim
# re-executes its base interpreter, hands it the work, and waits.
HANDED_OFF_HELPER = (
    "import subprocess, sys;"
    f"subprocess.Popen([sys.executable, '-c', {HELPER!r}]);"
    "print('spawned')"
)
# A launcher that starts a helper and is killed while it is still alive.
LIVE_LAUNCHER = (
    "import pathlib, subprocess, sys, time;"
    f"p = subprocess.Popen([sys.executable, '-c', {HELPER!r}]);"
    "pathlib.Path('helper.txt').write_text(str(p.pid));"
    "time.sleep(30)"
)

PROFILE = {"btw": {"enabled": True, "work_loop": {"enabled": True}}}


def _agent(code: str, **overrides) -> dict:
    entry = {
        "id": "fake",
        "type": "custom",
        "enabled": True,
        "command": sys.executable,
        "extra_args": ["-c", code],
        "timeout_seconds": 30,
    }
    entry.update(overrides)
    return ca.normalize_coding_agents([entry])[0]


def test_the_workspace_root_follows_the_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path / "root"))
    configured = {"btw": {"work_loop": {"workspace_root": str(tmp_path / "tasks")}}}
    assert cr.workspace_root(configured) == tmp_path / "tasks"
    assert cr.workspace_root(PROFILE) == Path(tmp_path) / "root" / "data" / "btw" / (
        "workspaces"
    )
    assert (
        cr.workspace_root({"btw": {"work_loop": {"workspace_root": "  "}}})
        == Path(tmp_path) / "root" / "data" / "btw" / "workspaces"
    )
    assert (
        cr.workspace_root({"btw": "not a mapping"})
        == Path(tmp_path) / "root" / ("data") / "btw" / "workspaces"
    )


def test_a_folder_name_cannot_escape_the_root():
    assert cr.task_folder_name("abc123", "claude_code") == "abc123-claude_code"
    assert cr.task_folder_name("abc", "..") == "abc"
    assert cr.task_folder_name("../..", "x/y") == "x-y"
    assert cr.task_folder_name("///", "") == "task"
    assert cr.task_folder_name("abc", "agent", "run1") == "abc-agent-run1"


def test_a_workspace_is_created_inside_the_root(tmp_path):
    workspace = cr.task_workspace(tmp_path, "session-1", "claude_code")
    assert workspace.is_dir()
    assert workspace.parent == tmp_path
    assert workspace.name.startswith("session-1-claude_code-")


def test_each_delegation_gets_a_folder_of_its_own(tmp_path):
    first = cr.task_workspace(tmp_path, "session-1", "claude_code")
    second = cr.task_workspace(tmp_path, "session-1", "claude_code")
    assert first != second
    assert first.is_dir() and second.is_dir()


def test_the_task_file_keeps_the_task_text(tmp_path):
    path = cr.write_task_file(tmp_path, "  do the thing  ")
    assert path.read_text(encoding="utf-8") == "do the thing\n"


def test_the_child_gets_a_whitelisted_environment(monkeypatch):
    monkeypatch.setenv("ASTRBOT_SECRET_TOKEN", "provider-key-must-not-travel")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = cr.child_environment({"MY_AGENT_FLAG": "1"})
    assert "ASTRBOT_SECRET_TOKEN" not in env
    assert env["PATH"] == "/usr/bin"
    assert env["MY_AGENT_FLAG"] == "1"
    assert set(env) <= set(cr.CHILD_ENV_NAMES) | {"MY_AGENT_FLAG", "PYTHONIOENCODING"}


@pytest.mark.asyncio
async def test_the_child_does_not_inherit_astrbot_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTRBOT_SECRET_TOKEN", "provider-key-must-not-travel")
    agent = _agent("import os; print(os.environ.get('ASTRBOT_SECRET_TOKEN', 'absent'))")
    result = await cr.run_coding_task(agent, workspace=tmp_path, task="t")
    assert result.status == cr.STATUS_COMPLETED
    assert (tmp_path / cr.OUTPUT_LOG_NAME).read_text(encoding="utf-8").strip() == (
        "absent"
    )


@pytest.mark.asyncio
async def test_a_successful_run_reports_its_output_and_artifacts(tmp_path):
    result = await cr.run_coding_task(
        _agent(WRITE_AND_ECHO), workspace=tmp_path, task="write out.txt"
    )
    assert result.status == cr.STATUS_COMPLETED
    assert result.exit_code == 0
    assert result.detail == ""
    assert result.artifacts == ["out.txt"]
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "write out.txt"
    assert (tmp_path / cr.OUTPUT_LOG_NAME).read_text(encoding="utf-8").strip() == "done"


@pytest.mark.asyncio
async def test_a_custom_agent_reports_no_final_message(tmp_path):
    result = await cr.run_coding_task(
        _agent(WRITE_AND_ECHO), workspace=tmp_path, task="t"
    )
    assert result.output == ""


@pytest.mark.asyncio
async def test_a_nonzero_exit_is_a_failure(tmp_path):
    agent = _agent("import sys; sys.exit(3)")
    result = await cr.run_coding_task(agent, workspace=tmp_path, task="t")
    assert result.status == cr.STATUS_FAILED
    assert result.exit_code == 3
    assert "exited with code 3" in result.detail


@pytest.mark.asyncio
async def test_a_run_that_overruns_its_timeout_is_stopped(tmp_path):
    result = await cr.run_coding_task(
        _agent(SLEEP_FOREVER, timeout_seconds=1), workspace=tmp_path, task="t"
    )
    assert result.status == cr.STATUS_TIMED_OUT
    assert "ran longer than 1s" in result.detail
    assert result.exit_code is not None


def test_a_timed_out_claude_run_says_why_it_may_have_waited():
    """`-p` has no terminal, so an unapproved shell command waits forever.

    A timeout that only says "it took too long" leaves the operator with
    nothing to change; naming the likely cause is the difference between a
    mystery and a fix.
    """
    claude = {"type": "claude_code", "permission_mode": "acceptEdits"}
    assert "bypassPermissions" in cr._stall_hint(claude)
    # Nothing to explain when the run was already free to do everything, or
    # when the CLI is not the one with this shape.
    assert cr._stall_hint({**claude, "permission_mode": "bypassPermissions"}) == ""
    assert cr._stall_hint({"type": "codex", "permission_mode": "acceptEdits"}) == ""


@pytest.mark.asyncio
async def test_a_withdrawn_request_stops_waiting(tmp_path):
    result = await cr.run_coding_task(
        _agent(SLEEP_FOREVER),
        workspace=tmp_path,
        task="t",
        stop_requested=lambda: True,
    )
    assert result.status == cr.STATUS_CANCELLED
    assert result.detail == "The coding agent was stopped."


@pytest.mark.asyncio
async def test_a_command_that_cannot_start_is_a_failure(tmp_path):
    agent = ca.normalize_coding_agents(
        [
            {
                "id": "missing",
                "type": "custom",
                "enabled": True,
                "command": "definitely-not-a-real-binary-xyz",
            }
        ]
    )[0]
    result = await cr.run_coding_task(agent, workspace=tmp_path, task="t")
    assert result.status == cr.STATUS_FAILED
    assert result.exit_code is None
    assert "could not be started" in result.detail


async def _git(*args: str, cwd: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.wait()


@pytest.mark.asyncio
async def test_a_git_project_dir_reports_only_what_the_run_changed(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    await _git("init", "-q", cwd=repository)
    (repository / "tracked.txt").write_text("before", encoding="utf-8")
    await _git("add", "tracked.txt", cwd=repository)
    # Already dirty before the run: not this task's output.
    (repository / "already-dirty.txt").write_text("mine", encoding="utf-8")

    baseline = await cr.snapshot_artifacts(repository)
    (repository / "new.txt").write_text("after", encoding="utf-8")

    changed = await cr._git_artifacts(repository, baseline)
    assert changed == ["new.txt"]


@pytest.mark.asyncio
async def test_a_git_project_dir_reports_paths_the_run_committed(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    await _git("init", "-q", cwd=repository)
    await _git("config", "user.email", "btw@example.invalid", cwd=repository)
    await _git("config", "user.name", "BTW", cwd=repository)
    (repository / "tracked.txt").write_text("before", encoding="utf-8")
    await _git("add", "tracked.txt", cwd=repository)
    await _git("commit", "-q", "-m", "first", cwd=repository)

    baseline = await cr.snapshot_artifacts(repository)
    (repository / "committed.txt").write_text("after", encoding="utf-8")
    await _git("add", "committed.txt", cwd=repository)
    await _git("commit", "-q", "-m", "second", cwd=repository)

    changed = await cr._git_artifacts(repository, baseline)
    assert changed == ["committed.txt"]


@pytest.mark.asyncio
async def test_a_plain_folder_reports_only_what_the_run_wrote(tmp_path):
    cr.write_task_file(tmp_path, "t")
    (tmp_path / cr.OUTPUT_LOG_NAME).write_text("log", encoding="utf-8")
    (tmp_path / ca.LAST_MESSAGE_NAME).write_text("msg", encoding="utf-8")
    old = tmp_path / "old.txt"
    old.write_text("was here before", encoding="utf-8")
    stale = time.time() - 3600
    os.utime(old, (stale, stale))

    written = cr._files_written_since(tmp_path, time.time() - 60)
    assert written == []
    assert "old.txt" not in written


def test_a_file_written_on_the_boundary_is_still_reported(tmp_path):
    """A run's output must survive the two clocks disagreeing.

    A file's modification time comes from the filesystem and the run's start
    from `time.time()`.  They are not the same clock: on Windows the file one
    can read more than a millisecond behind, so a file written the instant
    after the snapshot can look older than the run that wrote it.
    """
    started_at = time.time()
    boundary = tmp_path / "written.txt"
    boundary.write_text("x", encoding="utf-8")
    just_before = started_at - 0.01
    os.utime(boundary, (just_before, just_before))
    assert cr._files_written_since(tmp_path, started_at) == ["written.txt"]

    # Leaning outward is a tolerance, not an amnesty: the operator's own files
    # stay out of the report.
    older = tmp_path / "older.txt"
    older.write_text("x", encoding="utf-8")
    stale = started_at - 3600
    os.utime(older, (stale, stale))
    assert cr._files_written_since(tmp_path, started_at) == ["written.txt"]


@pytest.mark.asyncio
async def test_a_delegated_run_reports_the_folder_and_the_project_dir(tmp_path):
    workspace = tmp_path / "workspace"
    project = tmp_path / "project"
    workspace.mkdir()
    project.mkdir()
    (project / "kept.txt").write_text("mine", encoding="utf-8")
    stale = time.time() - 3600
    os.utime(project / "kept.txt", (stale, stale))

    agent = _agent(
        "import pathlib;pathlib.Path('produced.txt').write_text('x')",
        project_dir=str(project),
    )
    result = await cr.run_coding_task(agent, workspace=workspace, task="t")
    # The project dir's own files are the operator's, not this run's output.
    assert result.artifacts == ["produced.txt"]


@pytest.mark.asyncio
async def test_an_absent_root_contributes_nothing(tmp_path):
    baseline = await cr.snapshot_artifacts(None)
    assert await cr.collect_artifacts(baseline, tmp_path / "missing") == []


@pytest.mark.asyncio
async def test_the_artifact_list_is_capped_and_says_so(tmp_path, caplog):
    for index in range(cr.MAX_ARTIFACTS + 5):
        (tmp_path / f"file-{index:03d}.txt").write_text("x", encoding="utf-8")
    baseline = await cr.snapshot_artifacts(None)
    with caplog.at_level("INFO"):
        artifacts = await cr.collect_artifacts(baseline, tmp_path)
    assert len(artifacts) == cr.MAX_ARTIFACTS
    assert "reporting the first" in caplog.text


@pytest.mark.asyncio
async def test_both_roots_are_read_for_artifacts(tmp_path):
    workspace = tmp_path / "workspace"
    project = tmp_path / "project"
    workspace.mkdir()
    project.mkdir()
    (workspace / "a.txt").write_text("x", encoding="utf-8")
    old = project / "before.txt"
    old.write_text("the operator's own file", encoding="utf-8")
    # Outside the window the run's task folder covers: the root is not a work
    # tree, so the start of the run is the only boundary it has.
    stale = time.time() - 3600
    os.utime(old, (stale, stale))

    baseline = await cr.snapshot_artifacts(project)
    (project / "b.txt").write_text("after", encoding="utf-8")

    assert await cr.collect_artifacts(baseline, workspace, project) == [
        "a.txt",
        "b.txt",
    ]


@pytest.mark.asyncio
async def test_a_finished_child_is_not_terminated_again():
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "pass", stdout=asyncio.subprocess.PIPE
    )
    await process.wait()
    await cr._terminate(ProcessTree(), process)
    assert process.returncode == 0


@pytest.mark.asyncio
async def test_a_cancelled_run_does_not_leave_the_agent_running(tmp_path):
    slow_writer = (
        "import pathlib, time;"
        "time.sleep(1.5);"
        "pathlib.Path('sentinel.txt').write_text('x', encoding='utf-8')"
    )
    task = asyncio.create_task(
        cr.run_coding_task(_agent(slow_writer), workspace=tmp_path, task="t")
    )
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        _ = await task

    # The child had most of its sleep left; a surviving one would still write.
    await asyncio.sleep(1.8)
    assert not (tmp_path / "sentinel.txt").exists()


@pytest.mark.asyncio
async def test_a_stopped_run_does_not_leave_helpers_writing(tmp_path):
    """A coding agent CLI is a tree; stopping the parent must stop the tree.

    Claude Code and Codex are a launcher plus a ``node`` process.  A stop that
    reaches only the launcher leaves the ``node`` child writing to the host
    after the work loop believes the run has ended.
    """
    agent = _agent(LIVE_LAUNCHER, timeout_seconds=1)
    result = await cr.run_coding_task(agent, workspace=tmp_path, task="t")
    assert result.status == cr.STATUS_TIMED_OUT

    # The helper sleeps far past this point; a surviving one writes sentinel.
    await asyncio.sleep(HELPER_SLEEP_SECONDS)
    assert not (tmp_path / "sentinel.txt").exists()


@pytest.mark.asyncio
async def test_a_run_that_ends_does_not_leave_helpers_writing(tmp_path):
    """The same tree, when the launcher exits on its own instead of being killed.

    Claude Code and Codex are a launcher plus a ``node`` process: the launcher
    starts the helper, hands it the work, and returns.  The run is over and the
    helper is not, so nothing that only stops the launcher would reach it.
    """
    agent = _agent(DETACHED_HELPER)
    result = await cr.run_coding_task(agent, workspace=tmp_path, task="t")
    assert result.status == cr.STATUS_COMPLETED

    # The helper is still sleeping; only a surviving one writes sentinel.
    await asyncio.sleep(HELPER_SLEEP_SECONDS)
    assert not (tmp_path / "sentinel.txt").exists()


@pytest.mark.asyncio
async def test_a_helper_on_the_launcher_streams_is_waited_out(tmp_path):
    """A helper holding the launcher's own streams is part of the run.

    Until it closes them the run has not finished reading, so the run reports
    only after it is done -- which is what keeps a launcher that returns at
    once from being reported as a finished run while its work goes on.
    """
    agent = _agent(HANDED_OFF_HELPER)
    result = await cr.run_coding_task(agent, workspace=tmp_path, task="t")
    assert result.status == cr.STATUS_COMPLETED

    # The helper wrote during the run, not after it, so the run waited for it.
    assert result.artifacts == ["sentinel.txt"]
