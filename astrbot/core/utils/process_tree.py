"""Start a child so that stopping it also stops everything it started.

A coding agent CLI is a launcher plus the processes it spawns: Claude Code and
Codex are a wrapper around ``node``.  Stopping only the process this program
started leaves that work running on the host, and a timeout or a withdrawn
request would then be a promise the runtime cannot keep.

POSIX has process groups for this: the child is made a session leader and the
whole group is signalled.  Windows has no equivalent -- ``taskkill /T`` walks a
parent/child snapshot and therefore misses a grandchild whose parent already
exited -- so on Windows the child is instead suspended at birth, bound to a Job
Object, and resumed.  The kernel then applies the job's
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` to everything the tree starts, including
children of children.

Suspending is what makes that reliable: an assignment that happens after the
child has started is a race, and a launcher that spawns ``node`` and exits
loses it -- the grandchild is already born outside the job and no later signal
can reach it.

This module owns both mechanisms so a caller has one way to start a child and
one way to stop it, whichever platform it is on.
"""

import asyncio
import contextlib
import ctypes
import subprocess
import sys
import threading
import time
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_int,
    c_longlong,
    c_size_t,
    c_ulonglong,
    c_void_p,
    sizeof,
    wintypes,
)
from typing import Any

from astrbot import logger

__all__ = ["ProcessTree", "ThreadAssigner"]

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x0800
# An assignment the kernel guarantees to make before the thread beside it runs.
_JOB_OBJECT_ASSIGN_TIMEOUT_MS = 2_000
_JOB_OBJECT_ASSIGN_POLL_SECONDS = 0.001
# How long the assigner thread gets to park, to bind a child, and to stop.
# The bind is a rendezvous the spawning thread waits on, so it is bounded in
# case the thread never reports back.
_ASSIGNER_START_TIMEOUT = 2.0
_ASSIGNER_ASSIGN_TIMEOUT = 5.0
_ASSIGNER_CLOSE_TIMEOUT = 2.0
# Suspending the child at birth is what makes the assignment race-free.
_CREATE_SUSPENDED = 0x00000004
_TH32CS_SNAPTHREAD = 0x00000004
_THREAD_SUSPEND_RESUME = 0x0002
# PROCESS_SUSPEND_RESUME | PROCESS_SET_QUOTA | PROCESS_TERMINATE, the access a
# job binding needs, plus SYNCHRONIZE, which is what lets the child be watched.
_PROCESS_ASSIGN_ACCESS = 0x00000002 | 0x0800 | 0x0100 | 0x0001 | 0x00100000
_INVALID_HANDLE_VALUE = -1
_ERROR_INSUFFICIENT_BUFFER = 122
# Terminating a job is a kill; there is no polite Windows form of it.
_JOB_TERMINATE_EXIT_CODE = 1


class _ThreadEntry32(Structure):
    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    )


class _BasicLimitInformation(Structure):
    _fields_ = (
        ("PerProcessUserTimeLimit", c_longlong),
        ("PerJobUserTimeLimit", c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", c_size_t),
        ("MaximumWorkingSetSize", c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    )


class _IoCounters(Structure):
    _fields_ = tuple(
        (name, c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    )


class _ExtendedLimitInformation(Structure):
    _fields_ = (
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", c_size_t),
        ("JobMemoryLimit", c_size_t),
        ("PeakProcessMemoryUsed", c_size_t),
        ("PeakJobMemoryUsed", c_size_t),
    )


def _kernel32() -> Any:
    """Return the Windows kernel library, or ``None`` off Windows."""
    if sys.platform != "win32":
        return None
    windll = getattr(ctypes, "WinDLL", None)
    return windll("kernel32", use_last_error=True) if windll else None


def _last_error() -> int:
    """Return the calling thread's last Win32 error.

    ``ctypes.get_last_error`` exists only on Windows and only when the library
    that failed was loaded with ``use_last_error``, so it is looked up rather
    than referenced: this module is imported on POSIX as well, where the name
    does not exist at all.
    """
    import ctypes

    getter = getattr(ctypes, "get_last_error", None)
    return int(getter()) if getter is not None else 0


_KERNEL32 = _kernel32()
# The call and argument types ctypes cannot infer, declared once at import so a
# wrong one fails here rather than as a misread handle at kill time.
if _KERNEL32 is not None:  # pragma: no cover - Windows only
    _KERNEL32.CreateJobObjectW.restype = wintypes.HANDLE
    _KERNEL32.CreateJobObjectW.argtypes = (c_void_p, wintypes.LPCWSTR)
    _KERNEL32.SetInformationJobObject.restype = wintypes.BOOL
    _KERNEL32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        c_int,
        c_void_p,
        wintypes.DWORD,
    )
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _KERNEL32.AssignProcessToJobObject.restype = wintypes.BOOL
    _KERNEL32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _KERNEL32.TerminateJobObject.restype = wintypes.BOOL
    _KERNEL32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _KERNEL32.IsProcessInJob.restype = wintypes.BOOL
    _KERNEL32.IsProcessInJob.argtypes = (
        wintypes.HANDLE,
        wintypes.HANDLE,
        POINTER(c_int),
    )
    _KERNEL32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _KERNEL32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    _KERNEL32.Thread32First.restype = wintypes.BOOL
    _KERNEL32.Thread32First.argtypes = (wintypes.HANDLE, c_void_p)
    _KERNEL32.Thread32Next.restype = wintypes.BOOL
    _KERNEL32.Thread32Next.argtypes = (wintypes.HANDLE, c_void_p)
    _KERNEL32.OpenThread.restype = wintypes.HANDLE
    _KERNEL32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _KERNEL32.ResumeThread.restype = wintypes.DWORD
    _KERNEL32.ResumeThread.argtypes = (wintypes.HANDLE,)
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = (wintypes.HANDLE,)


class ProcessTree:
    """The group or job that owns one child process and everything it starts.

    Create it before spawning, start the child with :meth:`spawn`, and call
    :meth:`stop` to end the whole tree and :meth:`close` once the run is over,
    whether it is still in use or not.
    """

    __slots__ = ("_job", "_assigner")

    def __init__(self, job: int | None = None) -> None:
        self._job = job
        self._assigner: ThreadAssigner | None = None

    @classmethod
    def create(cls) -> ProcessTree:
        """Return a tree whose child can be bound before the child is spawned."""
        if _KERNEL32 is None:
            return cls()
        job = _KERNEL32.CreateJobObjectW(None, None)
        if not job:
            logger.debug("Could not create a job object; the child is not bound.")
            return cls()
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | _JOB_OBJECT_LIMIT_BREAKAWAY_OK
        )
        if not _KERNEL32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            byref(limits),
            sizeof(limits),
        ):
            logger.debug("Could not configure the job object; closing it.")
            _KERNEL32.CloseHandle(job)
            return cls()
        return cls(job)

    async def arm(self) -> None:
        """Prepare the tree for a child that does not exist yet.

        Binding a child on Windows is a suspended ``CreateProcess`` plus a job
        assignment made from a different thread, so the plumbing has to be up
        before the spawn.  Putting it up here is what lets :meth:`spawn` hold
        the child until the binding is done.

        Off Windows this does nothing: a session leader is signalled, not
        adopted.
        """
        if self._job is None or _KERNEL32 is None:
            return
        assigner = ThreadAssigner(self)
        assigner.start()
        if not await assigner.ready():
            logger.debug("Job binding is unavailable; the child is not bound.")
            await assigner.close()
            return
        self._assigner = assigner

    def spawn_kwargs(self) -> dict[str, Any]:
        """Return the spawn flags that put the child in a group of its own.

        On Windows the flag detaches the child from this console, so a Ctrl+C
        aimed at AstrBot does not reach it and stopping it does not take
        AstrBot down.  An armed tree also suspends the child, which is what
        leaves room for the binding; :meth:`spawn` is what releases it again.
        On POSIX the flag makes the child a session leader, which is what lets
        a later stop signal its whole group.
        """
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP
            if self._assigner is not None:
                flags |= _CREATE_SUSPENDED
            return {"creationflags": flags}
        return {"start_new_session": True}

    async def spawn(self, *argv: str, **kwargs: Any) -> asyncio.subprocess.Process:
        """Start a child that belongs to this tree from its first instruction.

        The child is spawned, bound, and only then released.  Binding after a
        suspended child has been released is a race, and a coding agent CLI is a
        launcher: a child that reaches its own ``CreateProcess`` in the window
        between the two leaves a helper outside the job that nothing can later
        reach.  On an armed tree there is no window -- the child is resumed by
        :meth:`ThreadAssigner.assign`, which does not return until the job has
        been told about it.

        Args:
            *argv: The program and its arguments.
            **kwargs: Anything else ``create_subprocess_exec`` accepts.

        Returns:
            The running child.
        """
        kwargs.update(self.spawn_kwargs())
        process = await asyncio.create_subprocess_exec(*argv, **kwargs)
        assigner = self._assigner
        if assigner is None:
            # Unarmed: the child is already running, so the best that is left is
            # binding it from a thread that can wait on it.
            self._bind(process.pid)
        else:
            await assigner.assign(process.pid)
        return process

    def _bind(self, pid: int) -> None:
        """Assign one running child to this tree's job.

        The assignment itself runs off the event loop: a child that has already
        started cannot be bound from the thread that spawned it, but a thread
        that merely waits on that child can.
        """
        threading.Thread(target=self._bind_blocking, args=(pid,), daemon=True).start()

    def _bind_blocking(self, pid: int) -> None:
        """Assign one child to this tree's job, best effort."""
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE, the access a job needs.
        handle = _KERNEL32.OpenProcess(_PROCESS_ASSIGN_ACCESS, False, pid)
        if not handle:
            logger.debug(
                "Could not open the coding agent to bind it to its job: err=%s",
                _last_error(),
            )
            return
        try:
            if not _KERNEL32.AssignProcessToJobObject(self._job, handle):
                logger.debug(
                    "Could not bind the coding agent to its job: err=%s",
                    _last_error(),
                )
        finally:
            _KERNEL32.CloseHandle(handle)

    def stop(self, process: object, *, force: bool) -> None:
        """Signal the whole tree.

        Args:
            process: The child that was adopted by this tree.
            force: Whether to kill instead of asking.  Windows has no polite
                form of a tree stop, so both values kill there.
        """
        if _KERNEL32 is not None:
            self._stop_windows(process)
            return
        self._stop_posix(process, force=force)

    def _stop_windows(self, process: object) -> None:
        if self._job is not None and _KERNEL32.TerminateJobObject(
            self._job, _JOB_TERMINATE_EXIT_CODE
        ):
            return
        if self._job is not None:
            logger.debug("Could not terminate the job object; falling back.")
        pid = getattr(process, "pid", None)
        if not isinstance(pid, int):
            return
        try:
            subprocess.run(  # noqa: S603
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("Could not stop the coding agent's tree: %s", exc)

    def _stop_posix(self, process: object, *, force: bool) -> None:
        import os
        import signal

        pid = getattr(process, "pid", None)
        if isinstance(pid, int):
            group_signal = signal.SIGKILL if force else signal.SIGTERM
            try:
                os.killpg(pid, group_signal)
                return
            except ProcessLookupError:
                return
            except PermissionError:
                # macOS reports an already-reaped group this way; anything else
                # means the child is not a group leader, so fall through.
                pass
        try:
            if force:
                process.kill()  # type: ignore[attr-defined]
            else:
                process.terminate()  # type: ignore[attr-defined]
        except AttributeError, ProcessLookupError:
            return

    async def close(self) -> None:
        """Release the tree's own resources.

        Closing a job whose limit flag is ``KILL_ON_JOB_CLOSE`` ends whatever is
        still in it, which is the point: a run that finished while a helper it
        started kept going does not leave that helper behind.
        """
        assigner = self._assigner
        self._assigner = None
        if assigner is not None:
            await assigner.close()
        if self._job is not None and _KERNEL32 is not None:
            _KERNEL32.CloseHandle(self._job)
        self._job = None


class ThreadAssigner:
    """Bind a child to its job while the child is still suspended.

    Windows has to be told about a process after ``CreateProcess`` returns and
    before that process runs, and there is no flag to put a child in a job the
    way ``start_new_session`` puts it in a group.  A thread is started before
    the spawn and parked on its first instruction; the spawning thread hands it
    the ``(job, pid)`` pair and the two rendezvous there.

    Without that rendezvous the assignment races the child: a launcher that
    starts ``node`` and exits within it leaves the grandchild outside the job,
    where ``TerminateJobObject`` can never reach it.

    Binding is best effort. A child whose assignment the kernel refuses -- an
    already-running one on a machine that forbids job nesting, say -- is
    resumed and its tree falls back to killing the process directly.
    """

    __slots__ = ("_args", "_assigned", "_event", "_job", "_ready", "_thread")

    def __init__(self, tree: ProcessTree) -> None:
        self._job = tree._job
        self._args: tuple[int, int] | None = None
        self._event = threading.Event()
        self._ready = threading.Event()
        self._assigned = threading.Event()
        self._thread = threading.Thread(
            target=self._listener, name="process-tree-assigner", daemon=True
        )

    def start(self) -> None:
        """Start the listener; the child may not be spawned until it is ready."""
        self._thread.start()

    async def ready(self) -> bool:
        """Wait for the listener to be parked, so a spawn cannot outrun it."""
        return await asyncio.to_thread(self._ready.wait, _ASSIGNER_START_TIMEOUT)

    async def assign(self, pid: int) -> bool:
        """Hand one suspended child to the listener and wait for the binding.

        The child stays suspended until the listener resumes it, so returning
        from here means the job already knows about the child and about
        everything the child goes on to start.
        """
        if not self._thread.is_alive():  # pragma: no cover - listener crashed
            _resume(pid)
            return False
        job = self._job
        if job is None:  # pragma: no cover - an unarmed tree never gets here
            _resume(pid)
            return False
        self._args = (job, pid)
        self._event.set()
        await asyncio.to_thread(self._assigned.wait, _ASSIGNER_ASSIGN_TIMEOUT)
        return True

    async def close(self) -> None:
        """Stop the listener and let it go, whether or not it was ever used."""
        self._event.set()
        await asyncio.to_thread(self._thread.join, _ASSIGNER_CLOSE_TIMEOUT)

    def _listener(self) -> None:
        """Wait for a pid, bind it, and resume it."""
        try:
            self._ready.set()
            if not self._event.wait(_ASSIGNER_CLOSE_TIMEOUT):
                return
            if self._args is None:
                return  # Closing a tree that was never handed a child.
            self._assign(*self._args)
        except Exception:  # noqa: BLE001 - a broken listener must not crash the run
            logger.debug(
                "The job-binding thread stopped before reporting a result.",
                exc_info=True,
            )
        finally:
            self._assigned.set()

    def _assign(self, job: int, pid: int) -> None:
        """Bind one suspended process and let it go.

        The child is released whatever the assignment decides: it was created
        suspended, so nothing else is coming to start it.
        """
        handle = _KERNEL32.OpenProcess(_PROCESS_ASSIGN_ACCESS, False, pid)
        if not handle:
            logger.debug(
                "Could not open the coding agent to bind it to its job: err=%s",
                _last_error(),
            )
        else:
            try:
                done = bool(_KERNEL32.AssignProcessToJobObject(job, handle))
                if done:
                    done = _wait_until_in_job(handle, job)
                if not done:
                    logger.debug(
                        "Could not bind the coding agent to its job: err=%s",
                        _last_error(),
                    )
            finally:
                _KERNEL32.CloseHandle(handle)
        _resume(pid)


def _wait_until_in_job(handle: int, job: int) -> bool:
    """Return whether ``handle`` is in ``job``, waiting out a late assignment.

    Windows does not promise that a process is in its job the moment the
    assignment returns, so the caller samples the kernel until it is.
    """
    deadline = time.monotonic() + _JOB_OBJECT_ASSIGN_TIMEOUT_MS / 1000
    while True:
        in_job = c_int()
        if _KERNEL32.IsProcessInJob(handle, job, byref(in_job)):
            if in_job.value:
                return True
        elif _last_error() != _ERROR_INSUFFICIENT_BUFFER:
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(_JOB_OBJECT_ASSIGN_POLL_SECONDS)


def _resume(pid: int) -> None:
    """Start a process that was created suspended.

    The thread is looked up by owner rather than by the id ``CreateProcess``
    reported: on Windows 11 the thread that runs first is not always the one
    that was created with the process.
    """
    # TH31: SuspendThread reports failure by returning -1, not 0.
    with contextlib.suppress(OSError):
        snapshot = _KERNEL32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
        if snapshot == _INVALID_HANDLE_VALUE:
            logger.debug("Could not enumerate threads to release process %s.", pid)
            return
        try:
            entry = _ThreadEntry32()
            entry.dwSize = sizeof(entry)
            found = _KERNEL32.Thread32First(snapshot, byref(entry))
            while found:
                if entry.th32OwnerProcessID == pid:
                    handle = _KERNEL32.OpenThread(
                        _THREAD_SUSPEND_RESUME, False, entry.th32ThreadID
                    )
                    if handle:
                        try:
                            if _KERNEL32.ResumeThread(handle) == 0xFFFFFFFF:
                                logger.debug(
                                    "Could not resume a thread of process %s.", pid
                                )
                        finally:
                            _KERNEL32.CloseHandle(handle)
                found = _KERNEL32.Thread32Next(snapshot, byref(entry))
        finally:
            _KERNEL32.CloseHandle(snapshot)
