from pathlib import Path

import pytest

from scripts.nightly_release_notes import main, render_notes

IMAGE = "ghcr.io/xero-team/astrbot"
SHA = "f0a4fb53634d9381008ad303e95b30f067219b7f"
TAGS = ["nightly", "nightly-20260908", "sha-f0a4fb5"]


def test_render_notes_includes_pull_and_compose_commands() -> None:
    notes = render_notes(
        image=IMAGE,
        tags=TAGS,
        sha=SHA,
        commits=["feat(api): export TextPart.mark_as_temp (abc1234)"],
        mode="schedule",
    )

    assert "docker pull ghcr.io/xero-team/astrbot:nightly" in notes
    assert "docker pull ghcr.io/xero-team/astrbot:sha-f0a4fb5" in notes
    assert "image: ghcr.io/xero-team/astrbot:nightly" in notes
    assert "docker compose pull astrbot" in notes
    assert "Xero-Team fork" in notes
    assert "astrbot:local" in notes
    assert "feat(api): export TextPart.mark_as_temp (abc1234)" in notes
    assert SHA in notes
    assert "Do not add `build:`" in notes


def test_render_notes_dispatch_without_commits_states_manual_rebuild() -> None:
    notes = render_notes(
        image=IMAGE,
        tags=["nightly", "sha-f0a4fb5"],
        sha=SHA,
        commits=[],
        mode="dispatch",
    )

    assert "manual rebuild of the current HEAD" in notes
    assert SHA in notes


def test_render_notes_rejects_empty_tags() -> None:
    with pytest.raises(ValueError, match="At least one image tag"):
        render_notes(image=IMAGE, tags=[], sha=SHA, commits=[], mode="schedule")


def test_main_writes_notes_file(tmp_path: Path) -> None:
    output = tmp_path / "notes.md"
    commits = tmp_path / "commits.txt"
    commits.write_text("fix(docker): pin runtime digest (deadbee)\n", encoding="utf-8")

    assert (
        main(
            [
                "--image",
                IMAGE,
                "--tag",
                "nightly",
                "--tag",
                "sha-f0a4fb5",
                "--sha",
                SHA,
                "--mode",
                "dispatch",
                "--commits-file",
                str(commits),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    text = output.read_text(encoding="utf-8")
    assert "docker pull ghcr.io/xero-team/astrbot:nightly" in text
    assert "fix(docker): pin runtime digest (deadbee)" in text
