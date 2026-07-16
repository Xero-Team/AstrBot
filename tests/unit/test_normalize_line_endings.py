from subprocess import CompletedProcess

from scripts import normalize_line_endings


def test_normalize_line_endings_ignores_deleted_paths(monkeypatch, tmp_path) -> None:
    existing = tmp_path / "existing.md"
    existing.write_bytes(b"first\r\nsecond\rthird\n")

    def run(_command, **_kwargs):
        output = "i/lf    w/crlf  attr/text\texisting.md\n"
        output += "i/lf    w/crlf  attr/text\tdeleted.md\n"
        return CompletedProcess(_command, 0, stdout=output)

    monkeypatch.setattr(normalize_line_endings.subprocess, "run", run)

    assert normalize_line_endings.normalize_line_endings(tmp_path) == ["existing.md"]
    assert existing.read_bytes() == b"first\nsecond\nthird\n"
