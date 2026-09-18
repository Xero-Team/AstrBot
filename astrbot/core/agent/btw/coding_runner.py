"""Run one coding agent inside its own task folder and report what it produced.

The work loop cannot write, so every task that must change files lands here.
One run owns one folder: the task text is kept in it, the agent's whole
transcript is logged beside it, and whatever the agent changed is read back
from the folder afterwards.  Nothing outside that folder and the writable root
the agent was pointed at is touched by this module.

The child is started as its own process tree, because a coding agent CLI is a
launcher plus what it launches: Claude Code and Codex spawn ``node`` children
that would keep writing to the host after their parent was stopped.
"""

import asyncio
import codecs
import contextlib
import os
import re
import sys
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from astrbot import logger
from astrbot.core.agent.btw.coding_agents import (
    LAST_MESSAGE_NAME,
    TASK_FILE_NAME,
    agent_result_text,
    build_invocation,
    truncate_output,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.process_tree import ProcessTree

OUTPUT_LOG_NAME = "output.log"
# The files this module writes into the task folder.  They describe the run
# rather than being produced by it, so artifacts never report them.
TASK_BOOKKEEPING_FILES = frozenset({TASK_FILE_NAME, OUTPUT_LOG_NAME, LAST_MESSAGE_NAME})

# How often a running task checks whether the user withdrew it.
STOP_POLL_SECONDS = 0.5
# How long a terminated process gets to exit before it is killed outright.
TERMINATE_GRACE_SECONDS = 5.0
GIT_TIMEOUT_SECONDS = 10
# One runaway task must not flood the report with paths.
MAX_ARTIFACTS = 50
# What one child stream may keep in memory for the report.  The whole stream
# still reaches the run log on disk; only the tail is held here, because a
# thirty-minute ``stream-json`` run is not something to buffer whole.
MAX_CAPTURED_CHARS = 1_000_000
READ_CHUNK_BYTES = 64 * 1024
# How many entries a directory walk may visit before it stops.  A walk is
# capped so a large non-git root cannot turn one delegation into a long scan.
MAX_SCANNED_ENTRIES = 20_000
# A plain root's artifacts are separated from the operator's own files by
# comparing a file's modification time with the clock the run started on.  Those
# are two different clocks: on Windows the filesystem's is set from a coarser
# source and can lag ``time.time()`` by more than a millisecond, so a file the
# run wrote can read as older than the run.  The boundary therefore leans
# outward -- one of the operator's files attributed to the run is a smaller
# error than the run's own output going unreported.
MTIME_TOLERANCE_SECONDS = 0.05

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_TIMED_OUT = "timed_out"
STATUS_CANCELLED = "cancelled"

# The environment a coding agent CLI needs to start.  The child is a program on
# this host that talks to a provider with its own credential, so it gets none
# of AstrBot's own secrets: everything else the operator configures through the
# agent's ``env`` map.
CHILD_ENV_NAMES = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "USERNAME",
    "USER",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SystemRoot",
    "SystemDrive",
    "COMSPEC",
    "PATHEXT",
    "WINDIR",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "CODEX_HOME",
    # Where each CLI keeps its own login, when the operator runs one that is
    # not AstrBot's default location.  These are the CLIs' own state, not ours.
    "CLAUDE_CONFIG_DIR",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
)


@dataclass(slots=True)
class CodingTaskResult:
    """What one delegated run produced.

    Attributes:
        status: One of the module's ``STATUS_*`` values.
        exit_code: The child's exit code, or ``None`` when it never exited.
        workspace: The task folder the agent ran in.
        artifacts: Paths the run created or changed, relative to their root.
        output: The agent's own final message, already truncated.
        detail: A safe one-line reason when the run did not complete cleanly.
    """

    status: str
    exit_code: int | None
    workspace: Path
    artifacts: list[str] = field(default_factory=list)
    output: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ArtifactBaseline:
    """What the writable root outside the task folder held before the run.

    A ``project_dir`` belongs to the operator, so it is full of files this run
    never touched.  Reading it back without a "before" reading would report the
    operator's own work as the task's output.
    """

    started_at: float
    # ``git status --porcelain`` and ``HEAD`` before the run, when the root is
    # a work tree; ``None`` when it is not one.
    git_status: str | None = None
    git_head: str | None = None


def workspace_root(profile: Mapping) -> Path:
    """Return the directory that holds every delegated task folder.

    Args:
        profile: The current configuration profile.

    Returns:
        The configured root, or AstrBot's own data directory when unset.
    """
    btw = profile.get("btw", {})
    work = btw.get("work_loop", {}) if isinstance(btw, Mapping) else {}
    configured = work.get("workspace_root", "") if isinstance(work, Mapping) else ""
    if isinstance(configured, str) and configured.strip():
        return Path(configured.strip())
    return Path(get_astrbot_data_path()) / "btw" / "workspaces"


def task_folder_name(session_id: str, agent_id: str, run_id: str = "") -> str:
    """Return a filesystem-safe folder name for one delegated run.

    The session id comes from the runtime, but the agent id comes from a
    profile, so the joined name is sanitized rather than trusted: a configured
    id must not be able to place the folder outside the configured root.
    """
    parts = [str(session_id), str(agent_id), str(run_id)]
    raw = "-".join(part for part in parts if part)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-.")
    return safe[:96] or "task"


def task_workspace(root: Path, session_id: str, agent_id: str) -> Path:
    """Create and return the folder one delegated run owns.

    Every run is given its own folder, named for the session, the agent, and a
    fresh run id.  One work run may delegate more than once, and a second
    delegation must not land in the first one's folder, where it would overwrite
    the task file and the log and mix its files with the earlier run's.
    """
    for _ in range(3):
        folder = Path(root) / task_folder_name(
            session_id, agent_id, uuid.uuid4().hex[:12]
        )
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except FileExistsError:  # pragma: no cover - a 48-bit collision
            continue
        return folder
    raise OSError("Could not create a task folder for this run.")


def write_task_file(workspace: Path, task: str) -> Path:
    """Keep the task text in the folder it is carried out in."""
    path = workspace / TASK_FILE_NAME
    path.write_text(f"{task.strip()}\n", encoding="utf-8")
    return path


def child_environment(invocation_env: Mapping[str, str]) -> dict[str, str]:
    """Return the environment one coding agent CLI is started with.

    AstrBot's own environment holds provider keys and instance secrets, and the
    child is a third-party program that does not need them; they would also sit
    in the agent's own transcript and be logged with it.  The child is given
    instead the same system variables any shell would have, plus what the
    operator declared for this agent in its ``env`` map.

    Args:
        invocation_env: Environment entries the agent's profile declares.

    Returns:
        The complete environment for the child process.
    """
    child = {name: value for name in CHILD_ENV_NAMES if (value := os.environ.get(name))}
    child.update({str(key): str(value) for key, value in invocation_env.items()})
    if sys.platform != "win32":
        child.setdefault("PYTHONIOENCODING", "utf-8")
    return child


async def _terminate(tree: ProcessTree, process: asyncio.subprocess.Process) -> None:
    """Stop a child that outlived its task, its whole tree, and reap it.

    Reaping matters on POSIX: a child that is killed and never waited on stays
    a zombie for as long as AstrBot runs, and its process group keeps whatever
    it started alive.

    Closing the tree matters even when the launcher exited on its own, which is
    the usual case for a coding agent CLI: the run is over, but a helper the
    launcher started may still be writing.  Closing the tree is what ends
    whatever is left inside it.
    """
    if process.returncode is None:
        await asyncio.to_thread(tree.stop, process, force=False)
        if not await _reaped(process):
            await asyncio.to_thread(tree.stop, process, force=True)
            await _reaped(process)
    await tree.close()


async def _reaped(process: asyncio.subprocess.Process) -> bool:
    """Wait briefly for a stopped child to be reaped."""
    try:
        await asyncio.wait_for(process.wait(), TERMINATE_GRACE_SECONDS)
        return True
    except TimeoutError:
        return False


async def _drain(stream: asyncio.StreamReader | None, log) -> str:
    """Copy one child stream into the run log and return the tail of it.

    The log on disk keeps everything the child wrote.  Only a bounded tail is
    kept in memory, because a long ``stream-json`` run is arbitrarily large and
    the report never needs more than the end of it.
    """
    if stream is None:
        return ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    captured: deque[str] = deque()
    captured_chars = 0
    while chunk := await stream.read(READ_CHUNK_BYTES):
        text = decoder.decode(chunk)
        if not text:
            continue
        log.write(text)
        log.flush()
        captured.append(text)
        captured_chars += len(text)
        while captured_chars > MAX_CAPTURED_CHARS and len(captured) > 1:
            captured_chars -= len(captured.popleft())
    tail = decoder.decode(b"", final=True)
    if tail:
        log.write(tail)
        log.flush()
        captured.append(tail)
    return "".join(captured)


async def _wait_for_exit(
    tree: ProcessTree,
    process: asyncio.subprocess.Process,
    *,
    timeout_seconds: int,
    stop_requested: Callable[[], bool],
) -> str:
    """Wait for the child, honouring the run timeout and a withdrawn request.

    Returns:
        ``STATUS_COMPLETED`` when the child exited on its own, otherwise the
        status that explains why it was stopped.
    """
    waiter = asyncio.ensure_future(process.wait())
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    try:
        while not waiter.done():
            if stop_requested():
                await _terminate(tree, process)
                return STATUS_CANCELLED
            if loop.time() >= deadline:
                await _terminate(tree, process)
                return STATUS_TIMED_OUT
            await asyncio.wait({waiter}, timeout=STOP_POLL_SECONDS)
    finally:
        if not waiter.done():
            waiter.cancel()
    return STATUS_COMPLETED


async def _run_git(root: Path, *args: str) -> str | None:
    """Run one read-only git command in ``root`` and return its stdout."""
    process: asyncio.subprocess.Process | None = None
    tree = ProcessTree.create()
    await tree.arm()
    try:
        process = await tree.spawn(
            "git",
            "-C",
            str(root),
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), GIT_TIMEOUT_SECONDS)
    except TimeoutError:
        # A cancelled ``communicate`` leaves git running and holding the
        # index, so it has to be stopped rather than abandoned.
        if process is not None:
            await _terminate(tree, process)
        logger.debug("Git timed out while reading artifacts in %s.", root)
        return None
    except OSError as exc:
        logger.debug("Could not read git artifacts: %s", safe_error("", exc))
        return None
    finally:
        await tree.close()
    if process.returncode != 0:
        return None
    return stdout.decode("utf-8", errors="replace")


def _porcelain_paths(status: str) -> set[str]:
    """Return the paths one ``git status --porcelain`` reading names."""
    return {
        line[3:].strip()
        for line in status.splitlines()
        if len(line) > 3 and line[3:].strip()
    }


async def _git_state(root: Path) -> tuple[str, str] | None:
    """Return a work tree's ``(status, HEAD)``, or ``None`` when it is not one.

    A work tree whose ``HEAD`` does not resolve yet is still one: a folder the
    operator just ran ``git init`` in has a status and an empty history, and the
    files the run writes there are reported by that status.
    """
    if not (root / ".git").exists():
        return None
    status = await _run_git(root, "status", "--porcelain")
    if status is None:
        return None
    head = await _run_git(root, "rev-parse", "HEAD")
    if head is None:
        head = await _run_git(root, "rev-parse", "--verify", "-q", "HEAD")
    return status, (head or "").strip()


async def snapshot_artifacts(project_dir: Path | None) -> ArtifactBaseline:
    """Record what a run's writable root held before the run starts."""
    started_at = time.time()
    if project_dir is None:
        return ArtifactBaseline(started_at=started_at)
    state = await _git_state(project_dir)
    if state is None:
        return ArtifactBaseline(started_at=started_at)
    status, head = state
    return ArtifactBaseline(started_at=started_at, git_status=status, git_head=head)


def _listed_artifacts(root: Path) -> list[str]:
    """Return the files a plain task folder holds, minus this module's own."""
    artifacts: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts[0] in TASK_BOOKKEEPING_FILES:
            continue
        artifacts.append(relative.as_posix())
    return artifacts


def _files_written_since(root: Path, since: float) -> list[str]:
    """Return the files a plain root had written at or after ``since``.

    A root that is not a work tree has no record of what changed, and listing
    all of it would report the operator's own files as this task's output, so
    the run's start time is the boundary instead.  The walk is capped: a large
    root must not turn one delegation into an unbounded scan.
    """
    boundary = since - MTIME_TOLERANCE_SECONDS
    artifacts: list[str] = []
    visited = 0
    for path in sorted(root.rglob("*")):
        visited += 1
        if visited > MAX_SCANNED_ENTRIES:
            logger.warning(
                "Stopped scanning %s after %s entries; the artifact list may be "
                "incomplete.",
                root,
                MAX_SCANNED_ENTRIES,
            )
            break
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts[0] in TASK_BOOKKEEPING_FILES:
            continue
        try:
            if path.stat().st_mtime < boundary:
                continue
        except OSError:
            continue
        artifacts.append(relative.as_posix())
    return artifacts


async def _git_artifacts(root: Path, baseline: ArtifactBaseline) -> list[str] | None:
    """Return the paths a run changed in one work tree, or ``None`` if it is not one."""
    state = await _git_state(root)
    if state is None:
        return None
    status, head = state
    # Files that were already dirty before the run are not this run's output.
    changed = _porcelain_paths(status) - _porcelain_paths(baseline.git_status or "")
    if baseline.git_head and head != baseline.git_head:
        # The run committed, which cleans those paths out of the status above;
        # the commit range is what names them.
        committed = await _run_git(root, "diff", "--name-only", baseline.git_head, head)
        if committed is not None:
            changed.update(
                line.strip() for line in committed.splitlines() if line.strip()
            )
    return sorted(changed)


async def collect_artifacts(
    baseline: ArtifactBaseline,
    workspace: Path,
    project_dir: Path | None = None,
) -> list[str]:
    """Return the paths a delegated run created or changed.

    The task folder is created for the run, so everything in it that is not
    this module's own bookkeeping is the run's output.  A ``project_dir`` is
    the operator's own directory: it is read as a difference against the
    snapshot taken before the run, never as a listing of itself.

    Args:
        baseline: What the run's writable root held before it started.
        workspace: The task folder the agent ran in.
        project_dir: An additional root the agent was allowed to write to.

    Returns:
        Root-relative paths, in a stable order.
    """
    artifacts: list[str] = _listed_artifacts(workspace)
    if project_dir is not None and project_dir.is_dir():
        changed = await _git_artifacts(project_dir, baseline)
        artifacts.extend(
            changed
            if changed is not None
            else _files_written_since(project_dir, baseline.started_at)
        )
    unique = sorted(dict.fromkeys(artifacts))
    if len(unique) > MAX_ARTIFACTS:
        logger.info(
            "Coding task produced %s artifacts; reporting the first %s.",
            len(unique),
            MAX_ARTIFACTS,
        )
        unique = unique[:MAX_ARTIFACTS]
    return unique


def _stall_hint(agent: Mapping) -> str:
    """Explain the timeout a non-interactive Claude Code run is likely to hit.

    Claude Code is started with ``-p``, so there is no terminal to answer a
    permission prompt.  ``acceptEdits`` approves edits and nothing more, so a
    task that runs a shell command -- a test suite, a git command -- is waiting
    on an answer that can never come, and only stops when the run times out.
    Saying so turns an unexplained hang into something an operator can fix.
    """
    if str(agent.get("type", "")) != "claude_code":
        return ""
    if str(agent.get("permission_mode", "")) == "bypassPermissions":
        return ""
    return (
        " A non-interactive Claude Code run approves edits only, so a task that "
        "ran a shell command may have been waiting on a permission nothing can "
        "grant; bypassPermissions is what lets those run, and it is only for a "
        "task folder that can be discarded."
    )


async def run_coding_task(
    agent: Mapping,
    *,
    workspace: Path,
    task: str,
    stop_requested: Callable[[], bool] | None = None,
) -> CodingTaskResult:
    """Run one coding agent on one task and report the outcome.

    Args:
        agent: A normalized coding-agent entry.
        workspace: The task folder to run in.
        task: The complete task text.
        stop_requested: Polled while the child runs, so a withdrawn request
            stops waiting instead of running to completion.

    Returns:
        The run's status, exit code, artifacts, and final message.  A run that
        could not start at all reports a failure rather than raising.
    """
    project_dir = str(agent.get("project_dir", ""))
    write_task_file(workspace, task)
    invocation = build_invocation(agent, workspace=workspace)
    baseline = await snapshot_artifacts(Path(project_dir) if project_dir else None)
    is_stopped = stop_requested or (lambda: False)
    tree = ProcessTree.create()
    await tree.arm()
    try:
        process = await tree.spawn(
            *invocation.argv,
            cwd=str(invocation.cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_environment(invocation.env),
        )
    except OSError as exc:
        await tree.close()
        logger.error("Coding agent could not start: %s", safe_error("", exc))
        return CodingTaskResult(
            status=STATUS_FAILED,
            exit_code=None,
            workspace=workspace,
            detail=f"Coding agent {agent.get('command')!r} could not be started.",
        )

    stdout_text = ""
    with (workspace / OUTPUT_LOG_NAME).open("w", encoding="utf-8") as log:
        if process.stdin is not None:
            process.stdin.write(task.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
        stdout_task = asyncio.ensure_future(_drain(process.stdout, log))
        stderr_task = asyncio.ensure_future(_drain(process.stderr, log))
        try:
            status = await _wait_for_exit(
                tree,
                process,
                timeout_seconds=int(agent.get("timeout_seconds", 0)) or 1,
                stop_requested=is_stopped,
            )
            stdout_text, _stderr_text = await asyncio.gather(stdout_task, stderr_task)
        finally:
            for pending in (stdout_task, stderr_task):
                if not pending.done():
                    pending.cancel()
            # Timeout and cancellation are reaped above.  An unexpected error
            # arrives here instead.  Either way a coding agent left running
            # would keep writing to the host after the work loop stopped
            # tracking it, and a run that ended on its own is not the same as
            # the work it handed to a helper being over.  The shield lets the
            # reap finish while this task unwinds.
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(_terminate(tree, process))

    last_message = ""
    last_message_path = workspace / LAST_MESSAGE_NAME
    if last_message_path.is_file():
        last_message = last_message_path.read_text(encoding="utf-8", errors="replace")
    detail = ""
    if status == STATUS_TIMED_OUT:
        detail = f"The coding agent ran longer than {agent.get('timeout_seconds')}s."
        detail += _stall_hint(agent)
    elif status == STATUS_CANCELLED:
        detail = "The coding agent was stopped."
    elif process.returncode != 0:
        detail = f"The coding agent exited with code {process.returncode}."
        status = STATUS_FAILED
    return CodingTaskResult(
        status=status,
        exit_code=process.returncode,
        workspace=workspace,
        artifacts=await collect_artifacts(
            baseline, workspace, Path(project_dir) if project_dir else None
        ),
        output=truncate_output(
            agent_result_text(agent, stdout_text, last_message),
            int(agent.get("max_output_chars", 0)) or 1,
        ),
        detail=detail,
    )
