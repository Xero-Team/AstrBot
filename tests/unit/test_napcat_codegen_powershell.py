from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def _run_powershell_script(
    script_relative_path: str, *args: str
) -> subprocess.CompletedProcess[str]:
    if POWERSHELL is None:
        raise AssertionError("PowerShell executable is not available")

    script_path = REPO_ROOT / script_relative_path
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            *args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _normalize_powershell_output(text: str | None) -> str:
    return " ".join((text or "").split())


def _compact_for_path_match(text: str) -> str:
    return text.replace(" ", "")


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_generate_ob11_event_schema_rejects_empty_type_name() -> None:
    proc = _run_powershell_script(
        "scripts/napcat/generate_ob11_event_schema.ps1",
        "-TypeName",
        "",
    )

    assert proc.returncode != 0
    assert "TypeName must not be empty." in (proc.stderr or proc.stdout)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_generate_ob11_event_models_rejects_same_input_and_output(
    tmp_path: Path,
) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text('{"type":"object","properties":{}}', encoding="utf-8")

    proc = _run_powershell_script(
        "scripts/napcat/generate_ob11_event_models.ps1",
        "-SchemaPath",
        str(schema_path),
        "-OutputPath",
        str(schema_path),
    )

    assert proc.returncode != 0
    assert "SchemaPath and OutputPath must be different." in (
        proc.stderr or proc.stdout
    )


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_normalize_ob11_event_schema_rejects_invalid_json(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    output_path = tmp_path / "normalized.json"
    schema_path.write_text("{", encoding="utf-8")

    proc = _run_powershell_script(
        "scripts/napcat/normalize_ob11_event_schema.ps1",
        "-SchemaPath",
        str(schema_path),
        "-OutputPath",
        str(output_path),
    )

    assert proc.returncode != 0
    output = _normalize_powershell_output(proc.stderr or proc.stdout)
    assert "normalize_ob11_event_schema.py failed for" in output
    assert str(schema_path) in _compact_for_path_match(output)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is not available")
def test_generate_ob11_event_models_rejects_invalid_json(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    output_path = tmp_path / "models.py"
    schema_path.write_text("{", encoding="utf-8")

    proc = _run_powershell_script(
        "scripts/napcat/generate_ob11_event_models.ps1",
        "-SchemaPath",
        str(schema_path),
        "-OutputPath",
        str(output_path),
    )

    assert proc.returncode != 0
    output = _normalize_powershell_output(proc.stderr or proc.stdout)
    assert "Schema file is not valid JSON:" in output
    assert str(schema_path) in _compact_for_path_match(output)
