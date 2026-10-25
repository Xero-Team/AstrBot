import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / ".agents/skills/archify/renderers/shared/brand-marks.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")
def test_archify_ipv6_private_addresses_are_expanded_before_classification():
    cases = {
        "::1": True,
        "0:0:0:0:0:0:0:1": True,
        "::0001": True,
        "::": True,
        "::ffff:0:127.0.0.1": True,
        "::ffff:7f00:1": True,
        "fec0::1": True,
        "fc00::1": True,
        "fe80::1": True,
        "2001:db8::1": True,
        "8.8.8.8": False,
        "2606:4700:4700::1111": False,
    }
    script = f"""
import {{ isPrivateBrandAddress }} from {json.dumps(MODULE.as_uri())};
const input = {json.dumps(cases)};
console.log(JSON.stringify(Object.fromEntries(
  Object.keys(input).map((key) => [key, isPrivateBrandAddress(key)])
)));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert actual == cases
