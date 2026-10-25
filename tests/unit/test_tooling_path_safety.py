import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCAFFOLD = ROOT / ".agents/skills/create-astrbot-plugin/scripts/scaffold_plugin.py"
OPEN_ARTIFACT = ROOT / ".agents/skills/archify/bin/open-artifact.mjs"


def test_scaffold_refuses_an_ancestor_of_the_checkout(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.15"\n',
        encoding="utf-8",
    )
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCAFFOLD),
            "--output",
            str(tmp_path),
            "--name",
            "demo",
            "--author",
            "author",
            "--description",
            "description",
            "--astrbot-root",
            str(checkout),
            "--force",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "ancestor" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_windows_open_artifact_passes_target_through_environment(tmp_path):
    target = tmp_path / "artifact; calc.exe.html"
    target.write_text("ok", encoding="utf-8")
    script = f"""
import {{ openArtifact }} from {json.dumps(OPEN_ARTIFACT.as_uri())};
const calls = [];
const result = openArtifact({json.dumps(str(target))}, {{
  platform: 'win32',
  spawn(command, args, options) {{
    calls.push({{ command, args, env: options.env }});
    return {{ status: 0 }};
  }},
}});
console.log(JSON.stringify({{ calls, result }}));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    call = payload["calls"][0]
    assert call["command"] == "powershell.exe"
    assert str(target) not in call["args"]
    assert call["env"]["ASTRBOT_OPEN_TARGET"] == str(target)
