from pathlib import Path
from subprocess import CompletedProcess

from scripts import doctor


def test_version_runs_resolved_executable(monkeypatch, tmp_path: Path) -> None:
    resolved = str(tmp_path / "corepack.cmd")
    invoked: tuple[str, ...] | None = None

    monkeypatch.setattr(doctor.shutil, "which", lambda _command: resolved)

    def run(command, **_kwargs):
        nonlocal invoked
        invoked = command
        return CompletedProcess(command, 0, stdout="0.34.7\n", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", run)

    assert doctor.version(("corepack", "--version"), tmp_path) == "0.34.7"
    assert invoked == (resolved, "--version")


def test_version_treats_process_start_failure_as_missing(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _command: "stale-command")

    def run(_command, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(doctor.subprocess, "run", run)

    assert doctor.version(("corepack", "--version"), tmp_path) is None
