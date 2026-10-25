"""Linux filesystem deny mask integration."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

import pytest

from astrbot.core.computer.local_policy import (
    LocalFilesystemPolicy,
    LocalNetworkPolicy,
    LocalSandboxPolicy,
    LocalUnixSocketPolicy,
)
from astrbot.core.computer.process_sandbox import SandboxSpec, create_process_sandbox

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux bubblewrap filesystem tests require Linux.",
)


def _spec(
    workspace: Path,
    *,
    scope: str = "workspace",
    deny_read: tuple[str, ...] = (),
    deny_write: tuple[str, ...] = (),
) -> SandboxSpec:
    return SandboxSpec(
        workspace=workspace,
        policy=LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope=scope,  # type: ignore[arg-type]
            network=LocalNetworkPolicy(mode="off"),
            filesystem=LocalFilesystemPolicy(
                deny_read=deny_read,
                deny_write=deny_write,
            ),
            unix_sockets=LocalUnixSocketPolicy(mode="deny"),
        ),
    )


def _run(code: str, spec: SandboxSpec, tmp_path: Path):
    return create_process_sandbox().run(
        [sys.executable, "-c", code],
        spec,
        timeout=20,
        env={"HOME": str(tmp_path)},
    )


@pytest.mark.parametrize("scope", ["workspace", "host"])
def test_read_and_write_denies_apply_in_both_scopes(tmp_path: Path, scope: str) -> None:
    secret = tmp_path / "secret"
    secret.mkdir()
    secret_file = secret / "token"
    secret_file.write_text("TOPSECRET", encoding="utf-8")
    allowed = tmp_path / "allowed.txt"
    allowed.write_text("visible", encoding="utf-8")
    code = f"""
from pathlib import Path
secret = Path({str(secret_file)!r})
allowed = Path({str(allowed)!r})
try:
    print(secret.read_text())
except OSError as exc:
    print("read-denied", exc.errno)
try:
    secret.write_text("changed")
except OSError as exc:
    print("write-denied", exc.errno)
print("allowed", allowed.read_text())
"""
    result = _run(
        code,
        _spec(
            tmp_path,
            scope=scope,
            deny_read=(str(secret),),
            deny_write=(str(secret),),
        ),
        tmp_path,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"TOPSECRET" not in result.stdout
    assert b"allowed visible" in result.stdout
    assert secret_file.read_text() == "TOPSECRET"


def test_deny_wins_over_overlapping_workspace_and_python_grants(tmp_path: Path) -> None:
    (tmp_path / "secret").mkdir()
    secret = tmp_path / "secret" / "value"
    secret.write_text("TOPSECRET", encoding="utf-8")
    result = _run(
        f"from pathlib import Path\ntry:\n print(Path({str(secret)!r}).read_text())\nexcept OSError as exc:\n print('denied', exc.errno)\n",
        _spec(tmp_path, deny_read=(str(tmp_path / "secret"),)),
        tmp_path,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"TOPSECRET" not in result.stdout
    assert b"denied" in result.stdout


def test_glob_matching_is_launch_time_only(tmp_path: Path) -> None:
    denied = tmp_path / "denied"
    denied.mkdir()
    existing = denied / "existing.txt"
    existing.write_text("old", encoding="utf-8")
    code = f"""
from pathlib import Path
denied = Path({str(denied)!r})
try:
    print("existing", (denied / "existing.txt").read_text())
except OSError as exc:
    print("existing-denied", exc.errno)
(denied / "new.txt").write_text("new")
print("new", (denied / "new.txt").read_text())
"""
    result = _run(code, _spec(tmp_path, deny_read=(str(denied / "*.txt"),)), tmp_path)
    assert result.returncode == 0, result.stderr.decode()
    assert b"old" not in result.stdout
    assert b"new new" in result.stdout


def test_preexisting_hard_link_alias_documents_the_boundary(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("ALIASED", encoding="utf-8")
    alias = tmp_path / "alias.txt"
    os.link(secret, alias)
    result = _run(
        f"from pathlib import Path\ntry:\n print('alias', Path({str(alias)!r}).read_text())\nexcept OSError as exc:\n print('denied', exc.errno)\n",
        _spec(tmp_path, deny_read=(str(secret),)),
        tmp_path,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert b"alias ALIASED" in result.stdout


def test_denied_directory_uses_ephemeral_tmpfs(tmp_path: Path) -> None:
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / "value").write_text("TOPSECRET", encoding="utf-8")
    code = f"""
from pathlib import Path
hidden = Path({str(hidden)!r})
print("entries", list(hidden.iterdir()))
(hidden / "created").write_text("ephemeral")
print("created", (hidden / "created").read_text())
"""
    result = _run(code, _spec(tmp_path, deny_read=(str(hidden),)), tmp_path)
    assert result.returncode == 0, result.stderr.decode()
    assert b"TOPSECRET" not in result.stdout
    assert b"entries []" in result.stdout
    assert not (hidden / "created").exists()
    assert shlex.quote(str(hidden)) == shlex.quote(str(hidden))
