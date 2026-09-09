from pytest import MonkeyPatch

from scripts.prepare_release import ReleaseError, is_version_tag, latest_tag


def test_is_version_tag_accepts_semver_and_v_prefix() -> None:
    assert is_version_tag("4.27.5")
    assert is_version_tag("v4.27.5")
    assert is_version_tag("4.26.0-beta.8")
    assert not is_version_tag("nightly-20260908")
    assert not is_version_tag("nightly-manual-abc1234")
    assert not is_version_tag("sha-deadbee")


def test_latest_tag_skips_nightly_and_returns_version(
    monkeypatch: MonkeyPatch,
) -> None:
    def fake_git(args: list[str], *, capture_output: bool = False) -> str:
        del capture_output
        assert args == ["tag", "--merged", "HEAD", "--sort=-creatordate"]
        return "nightly-20260908\nv4.27.5\n4.26.0-beta.8\n"

    monkeypatch.setattr("scripts.prepare_release.git", fake_git)
    assert latest_tag() == "v4.27.5"


def test_latest_tag_empty_when_only_nightly(monkeypatch: MonkeyPatch) -> None:
    def fake_git(args: list[str], *, capture_output: bool = False) -> str:
        del args, capture_output
        return "nightly-20260909\nnightly-manual-abc1234\n"

    monkeypatch.setattr("scripts.prepare_release.git", fake_git)
    assert latest_tag() == ""


def test_latest_tag_empty_when_git_fails(monkeypatch: MonkeyPatch) -> None:
    def fake_git(args: list[str], *, capture_output: bool = False) -> str:
        del args, capture_output
        raise ReleaseError("git tag failed")

    monkeypatch.setattr("scripts.prepare_release.git", fake_git)
    assert latest_tag() == ""
