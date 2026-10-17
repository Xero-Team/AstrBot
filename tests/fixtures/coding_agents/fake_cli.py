"""A deterministic coding-agent CLI used by the BTW stream contract tests.

The first argument is the NDJSON fixture to replay.  The script reads the task
from stdin, writes one artifact, and optionally writes Codex's ``-o`` file.
Each line is flushed separately so the runner sees the stream while the child
is still alive rather than only after it exits.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

fixture = pathlib.Path(sys.argv[1])
task = sys.stdin.read()
pathlib.Path("report.md").write_text(task or "fixture task\n", encoding="utf-8")

# Codex receives ``-o last_message.txt`` from the real invocation.  The fake
# CLI writes the same file unconditionally so the runner's fallback contract is
# exercised even when a test supplies its own invocation.
pathlib.Path("last_message.txt").write_text("fixture final\n", encoding="utf-8")

for line in fixture.read_text(encoding="utf-8").splitlines():
    print(line, flush=True)
    time.sleep(0.01)

if stderr := os.environ.get("ASTRBOT_FAKE_STDERR"):
    print(stderr, file=sys.stderr, flush=True)
