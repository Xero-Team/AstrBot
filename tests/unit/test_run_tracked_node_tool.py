from subprocess import CompletedProcess

from scripts import run_tracked_node_tool


def test_tracked_files_ignores_deleted_paths(monkeypatch, tmp_path) -> None:
    existing = tmp_path / "existing.md"
    existing.touch()

    def run(_command, **_kwargs):
        return CompletedProcess(_command, 0, stdout=b"existing.md\0deleted.md\0")

    monkeypatch.setattr(run_tracked_node_tool.subprocess, "run", run)

    assert run_tracked_node_tool.tracked_files(tmp_path, ["*.md"]) == ["existing.md"]
