import os
from pathlib import Path

import pytest

from astrbot.core.skills._skill_fs import read_nofollow_capped


@pytest.mark.skipif(os.name == "nt", reason="FIFO creation is POSIX-only")
def test_skill_reader_does_not_block_on_fifo(tmp_path: Path):
    fifo = tmp_path / "SKILL.md"
    os.mkfifo(fifo)

    with pytest.raises(OSError):
        read_nofollow_capped(tmp_path, "SKILL.md")
