import subprocess
import sys
from pathlib import Path


def test_tokenizer_import_suppresses_jieba_syntax_warnings():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error::SyntaxWarning",
            "-c",
            "import astrbot.core.knowledge_base.retrieval.tokenizer",
        ],
        capture_output=True,
        cwd=repo_root,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
