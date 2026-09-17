"""Tests for writing a provider preset into a CLI's own global config."""

import json
import os

import pytest

from astrbot.core.agent.btw import cli_global_config as cg


@pytest.fixture
def homes(tmp_path, monkeypatch):
    """Point both CLIs at directories of the test's own."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return tmp_path


PROVIDER = {
    "id": "gw",
    "name": "Gateway",
    "base_url": "https://gw.example",
    "api_key": "sk-secret",
    "model": "opus",
    "wire_api": "responses",
}


def test_an_unknown_cli_is_refused(homes):
    with pytest.raises(ValueError):
        cg.target_path("nope")
    with pytest.raises(ValueError):
        cg.apply_provider("nope", {**PROVIDER, "api_key": ""})


def test_a_provider_without_an_endpoint_or_key_is_refused(homes):
    with pytest.raises(ValueError):
        cg.apply_provider("claude_code", {"id": "a", "base_url": "", "api_key": ""})
    with pytest.raises(ValueError):
        cg.apply_provider("claude_code", {"id": "", "base_url": "https://x"})


def test_claude_writes_the_endpoint_and_keeps_every_other_key(homes):
    path = cg.target_path("claude_code")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "env": {"ANTHROPIC_BASE_URL": "https://mine.example", "KEEP": "1"},
                "permissions": {"allow": ["Bash"]},
                "model": "sonnet",
            }
        ),
        encoding="utf-8",
    )

    state = cg.apply_provider("claude_code", {**PROVIDER, "api_key": ""})

    payload = json.loads(path.read_text(encoding="utf-8"))
    # The endpoint AstrBot manages is replaced...
    assert payload["env"]["ANTHROPIC_BASE_URL"] == "https://gw.example"
    assert payload["env"]["ANTHROPIC_MODEL"] == "opus"
    # ...and everything else is exactly as the user left it.
    assert payload["env"]["KEEP"] == "1"
    assert payload["permissions"] == {"allow": ["Bash"]}
    assert payload["model"] == "sonnet"
    assert state.managed is True
    assert state.base_url == "https://gw.example"
    assert state.model == "opus"


def test_a_credential_is_written_only_when_asked_for(homes):
    path = cg.target_path("claude_code")

    cg.apply_provider("claude_code", {**PROVIDER, "api_key": ""})
    assert (
        "ANTHROPIC_AUTH_TOKEN"
        not in json.loads(path.read_text(encoding="utf-8"))["env"]
    )

    state = cg.apply_provider("claude_code", PROVIDER)
    env = json.loads(path.read_text(encoding="utf-8"))["env"]
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-secret"
    assert state.has_credential is True
    if os.name != "nt":
        # A file holding a key is readable by its owner alone.  Windows does not
        # model the POSIX bits, so the check only means something elsewhere.
        assert path.stat().st_mode & 0o077 == 0


def test_a_state_never_carries_the_credential(homes):
    cg.apply_provider("claude_code", PROVIDER)
    state = cg.read_state("claude_code")
    assert "sk-secret" not in repr(state)


def test_an_unasked_credential_is_removed_rather_than_left_behind(homes):
    cg.apply_provider("claude_code", PROVIDER)
    cg.apply_provider("claude_code", {**PROVIDER, "api_key": ""})
    env = json.loads(cg.target_path("claude_code").read_text(encoding="utf-8"))["env"]
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_the_first_write_backs_the_file_up_once(homes):
    path = cg.target_path("claude_code")
    path.parent.mkdir(parents=True)
    original = json.dumps({"env": {"KEEP": "1"}})
    path.write_text(original, encoding="utf-8")

    cg.apply_provider("claude_code", {**PROVIDER, "api_key": ""})
    backup = path.with_name(path.name + cg.BACKUP_SUFFIX)
    assert backup.read_text(encoding="utf-8") == original

    # A second write does not clobber the original with AstrBot's own output.
    cg.apply_provider("claude_code", {**PROVIDER, "base_url": "https://other.example"})
    assert backup.read_text(encoding="utf-8") == original


def test_codex_keeps_the_users_comments_and_keys(homes):
    path = cg.target_path("codex")
    path.parent.mkdir(parents=True)
    path.write_text(
        '# my own settings\nmodel = "gpt-5"\n\n[mcp_servers.mine]\ncommand = "npx"\n',
        encoding="utf-8",
    )

    state = cg.apply_provider("codex", PROVIDER)

    text = path.read_text(encoding="utf-8")
    # The user's file survives, byte for byte, with AstrBot's section above it.
    assert "# my own settings" in text
    assert 'model = "gpt-5"' in text
    assert "[mcp_servers.mine]" in text
    assert text.index(cg.CODEX_MANAGED_BEGIN) < text.index("# my own settings")
    assert cg.CODEX_MANAGED_BEGIN in text and cg.CODEX_MANAGED_END in text
    assert 'base_url = "https://gw.example"' in text
    assert state.managed is True
    assert state.base_url == "https://gw.example"

    # The credential goes in auth.json under the name the section points at.
    auth = json.loads(
        (cg.codex_home() / cg.CODEX_AUTH_FILE).read_text(encoding="utf-8")
    )
    assert auth[cg.credential_env_name("gw")] == "sk-secret"
    assert "sk-secret" not in text


def test_rewriting_replaces_the_section_instead_of_stacking_it(homes):
    path = cg.target_path("codex")
    cg.apply_provider("codex", {**PROVIDER, "api_key": ""})
    cg.apply_provider("codex", {**PROVIDER, "base_url": "https://second.example"})
    text = path.read_text(encoding="utf-8")
    assert text.count(cg.CODEX_MANAGED_BEGIN) == 1
    second = "https://second.example"
    first = "https://gw.example"
    assert f'base_url = "{second}"' in text
    assert f'"{first}"' not in text


def test_a_truncated_section_is_left_alone(homes):
    path = cg.target_path("codex")
    path.parent.mkdir(parents=True)
    # No closing marker: AstrBot cannot know where the section ended, so it must
    # not guess and swallow the rest of the file.
    path.write_text(
        f'{cg.CODEX_MANAGED_BEGIN}\nbase_url = "https://x.example"\n[user]\n',
        encoding="utf-8",
    )
    state = cg.read_state("codex")
    assert state.managed is False


def test_an_unparseable_json_file_is_not_replaced_with_astrbots(homes):
    path = cg.target_path("claude_code")
    path.parent.mkdir(parents=True)
    path.write_text("{ this is not json", encoding="utf-8")

    # A backup is taken, so the damaged file is recoverable...
    cg.apply_provider("claude_code", {**PROVIDER, "api_key": ""})
    backup = path.with_name(path.name + cg.BACKUP_SUFFIX)
    assert backup.read_text(encoding="utf-8") == "{ this is not json"


def test_removing_restores_what_the_user_had(homes):
    path = cg.target_path("claude_code")
    path.parent.mkdir(parents=True)
    original = json.dumps({"env": {"KEEP": "1"}, "permissions": {}}, indent=2) + "\n"
    path.write_text(original, encoding="utf-8")

    cg.apply_provider("claude_code", PROVIDER)
    assert cg.read_state("claude_code").managed is True

    state = cg.remove_provider("claude_code")
    assert path.read_text(encoding="utf-8") == original
    assert state.managed is False
    assert not path.with_name(path.name + cg.BACKUP_SUFFIX).exists()


def test_removing_without_a_backup_takes_only_astrbots_keys(homes):
    path = cg.target_path("claude_code")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"env": {"KEEP": "1", "ANTHROPIC_BASE_URL": "https://gw.example"}}),
        encoding="utf-8",
    )
    path.with_name(path.name + cg.BACKUP_SUFFIX).unlink(missing_ok=True)

    cg.remove_provider("claude_code")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["env"] == {"KEEP": "1"}


def test_removing_a_codex_preset_drops_the_section_and_the_credential(homes):
    path = cg.target_path("codex")
    path.parent.mkdir(parents=True)
    path.write_text('# mine\nmodel = "gpt-5"\n', encoding="utf-8")

    cg.apply_provider("codex", PROVIDER)
    cg.remove_provider("codex")

    text = path.read_text(encoding="utf-8")
    assert cg.CODEX_MANAGED_BEGIN not in text
    assert "# mine" in text
    auth = json.loads(
        (cg.codex_home() / cg.CODEX_AUTH_FILE).read_text(encoding="utf-8")
    )
    assert cg.credential_env_name(PROVIDER["id"]) not in auth


def test_a_missing_file_reports_absent_rather_than_raising(homes):
    state = cg.read_state("claude_code")
    assert state.exists is False
    assert state.managed is False
    assert state.has_credential is False
