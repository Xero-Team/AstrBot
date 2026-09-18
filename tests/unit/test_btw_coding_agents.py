"""Tests for the coding-agent configuration and command lines."""

import json
from pathlib import Path

import pytest

from astrbot.core.agent.btw import coding_agents as ca


def _profile(agents: list, **work_overrides) -> dict:
    work = {"enabled": True, "coding_agents": agents, "computer_use_runtime": "local"}
    work.update(work_overrides)
    return {"btw": {"enabled": True, "work_loop": work}}


def _agent(**overrides) -> dict:
    entry = {
        "id": "claude_code",
        "name": "Claude Code",
        "type": "claude_code",
        "enabled": True,
        "command": "claude",
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Point every generated config at the test's own directories."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return tmp_path


def test_a_malformed_entry_is_dropped_not_raised():
    agents = ca.normalize_coding_agents(
        [
            "not a mapping",
            {"id": "", "type": "codex"},
            {"id": "no_type", "type": "unknown"},
            {"id": "no_command", "type": "custom"},
            _agent(),
        ]
    )
    assert [agent["id"] for agent in agents] == ["claude_code"]


def test_a_non_list_value_yields_no_agents():
    assert ca.normalize_coding_agents({"id": "x"}) == []
    assert ca.normalize_coding_agents(None) == []


def test_duplicate_ids_keep_the_first_entry():
    agents = ca.normalize_coding_agents([_agent(name="first"), _agent(name="second")])
    assert [agent["name"] for agent in agents] == ["first"]


def test_defaults_fill_in_every_field():
    agent = ca.normalize_coding_agents([_agent()])[0]
    assert agent["command"] == "claude"
    assert agent["permission_mode"] == ca.DEFAULT_PERMISSION_MODE
    assert agent["sandbox"] == ca.DEFAULT_SANDBOX
    assert agent["timeout_seconds"] == ca.DEFAULT_TIMEOUT_SECONDS
    assert agent["max_output_chars"] == ca.DEFAULT_MAX_OUTPUT_CHARS
    assert agent["extra_args"] == []
    assert agent["env"] == {}
    assert agent["active_provider"] == ""


def test_a_custom_agent_keeps_only_a_valid_command():
    agent = ca.normalize_coding_agents(
        [{"id": "mytool", "type": "custom", "command": "mytool", "enabled": True}]
    )[0]
    assert agent["command"] == "mytool"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("acceptEdits", "acceptEdits"),
        ("nonsense", ca.DEFAULT_PERMISSION_MODE),
        (None, ca.DEFAULT_PERMISSION_MODE),
    ],
)
def test_permission_mode_falls_back_to_a_safe_choice(raw, expected):
    agent = ca.normalize_coding_agents([_agent(permission_mode=raw)])[0]
    assert agent["permission_mode"] == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("read-only", "read-only"), ("nonsense", ca.DEFAULT_SANDBOX)],
)
def test_sandbox_falls_back_to_a_safe_choice(raw, expected):
    agent = ca.normalize_coding_agents([_agent(sandbox=raw)])[0]
    assert agent["sandbox"] == expected


def test_odd_field_types_fall_back_to_defaults():
    agent = ca.normalize_coding_agents(
        [
            _agent(
                name=12,
                enabled="yes",
                model=["x"],
                project_dir=7,
                extra_args=[1, "ok", ""],
                env={"A": "b", "C": 4, 5: "d"},
                timeout_seconds="60",
                max_output_chars=True,
            )
        ]
    )[0]
    assert agent["name"] == "claude_code"
    assert agent["enabled"] is False
    assert agent["model"] == ""
    assert agent["project_dir"] == ""
    assert agent["extra_args"] == ["ok"]
    assert agent["env"] == {"A": "b"}
    assert agent["timeout_seconds"] == 60
    assert agent["max_output_chars"] == ca.DEFAULT_MAX_OUTPUT_CHARS


def test_counts_below_their_minimum_are_clamped():
    agent = ca.normalize_coding_agents(
        [_agent(timeout_seconds=-5, max_output_chars=5)]
    )[0]
    assert agent["timeout_seconds"] == ca.MIN_TIMEOUT_SECONDS
    assert agent["max_output_chars"] == ca.MIN_MAX_OUTPUT_CHARS


def test_an_absent_count_falls_back_to_defaults():
    agent = ca.normalize_coding_agents(
        [_agent(timeout_seconds=0, max_output_chars=None)]
    )[0]
    assert agent["timeout_seconds"] == ca.DEFAULT_TIMEOUT_SECONDS
    assert agent["max_output_chars"] == ca.DEFAULT_MAX_OUTPUT_CHARS


def test_provider_presets_are_normalized_and_deduplicated():
    agent = ca.normalize_coding_agents(
        [
            _agent(
                providers=[
                    "nope",
                    {"id": "", "base_url": "x"},
                    {"id": "official"},
                    {"id": "official", "name": "dup"},
                    {
                        "id": "gw",
                        "base_url": " https://gw.example ",
                        "api_key": " sk-1 ",
                        "model": " m ",
                        "wire_api": "chat",
                    },
                    {"id": "plain", "wire_api": 5},
                ],
                active_provider="missing",
            )
        ]
    )[0]
    assert [p["id"] for p in agent["providers"]] == ["official", "gw", "plain"]
    assert agent["providers"][0]["name"] == "official"
    assert agent["providers"][1] == {
        "id": "gw",
        "name": "gw",
        "base_url": "https://gw.example",
        "api_key": "sk-1",
        "model": "m",
        "wire_api": "chat",
    }
    assert agent["providers"][2]["wire_api"] == "responses"
    # An unknown active provider falls back to the first preset.
    assert agent["active_provider"] == "official"


def test_enabled_agents_require_both_switches():
    agents = [_agent(), _agent(id="off", enabled=False)]
    assert ca.has_enabled_coding_agent(_profile(agents)) is True
    assert [agent["id"] for agent in ca.enabled_coding_agents(_profile(agents))] == [
        "claude_code"
    ]
    assert ca.has_enabled_coding_agent({"btw": {"enabled": False}}) is False
    assert ca.has_enabled_coding_agent("not a mapping") is False
    assert ca.has_enabled_coding_agent(_profile(agents, enabled=False)) is False


@pytest.mark.parametrize(
    "runtime",
    ["inherit", "none", "sandbox", "", "nonsense"],
)
def test_delegation_requires_a_local_runtime(runtime):
    """A delegated run is a process on this host, so no sandbox may claim it.

    The run is started by AstrBot directly instead of through the Computer Use
    booter, so a ``sandbox`` work loop would not contain it -- delegating there
    would be the way out of the sandbox rather than a use of it.
    """
    profile = _profile([_agent()], computer_use_runtime=runtime)
    assert ca.enabled_coding_agents(profile) == []
    assert ca.has_enabled_coding_agent(profile) is False
    assert ca.select_coding_agent(profile) is None


def test_selecting_an_agent_by_id_or_by_default():
    profile = _profile([_agent(), _agent(id="codex", type="codex", name="Codex")])
    assert ca.select_coding_agent(profile)["id"] == "claude_code"
    assert ca.select_coding_agent(profile, "codex")["id"] == "codex"
    assert ca.select_coding_agent(profile, "missing") is None
    assert ca.select_coding_agent({"btw": {"enabled": False}}) is None


def test_active_provider_resolves_the_configured_preset():
    agent = ca.normalize_coding_agents(
        [_agent(providers=[{"id": "gw"}], active_provider="gw")]
    )[0]
    assert ca.active_provider(agent)["id"] == "gw"
    assert ca.active_provider(_agent()) is None


def test_settings_home_lives_under_the_data_directory(isolated_paths):
    agent = ca.normalize_coding_agents([_agent()])[0]
    home = ca.settings_home(agent)
    assert home == Path(isolated_paths) / "root" / "data" / "btw" / "coding-agents" / (
        "claude_code"
    )
    assert (
        ca.settings_home({})
        == Path(isolated_paths) / "root" / "data" / "btw" / ("coding-agents") / "agent"
    )


def test_a_claude_invocation_carries_the_workspace_and_permissions(
    isolated_paths, tmp_path
):
    agent = ca.normalize_coding_agents(
        [
            _agent(
                model="opus",
                project_dir=str(tmp_path / "project"),
                extra_args=["--verbose"],
            )
        ]
    )[0]
    invocation = ca.build_invocation(agent, workspace=tmp_path)
    assert invocation.argv[:3] == ("claude", "-p", "--output-format")
    assert "--permission-mode" in invocation.argv
    assert invocation.argv[invocation.argv.index("--permission-mode") + 1] == (
        "acceptEdits"
    )
    assert invocation.argv[invocation.argv.index("--model") + 1] == "opus"
    assert invocation.argv[invocation.argv.index("--add-dir") + 1] == str(
        tmp_path / "project"
    )
    # A profile may extend the run, but a CLI takes the last of a repeated flag
    # and the managed ones come after, so the profile cannot talk them down.
    assert invocation.argv.index("--verbose") < invocation.argv.index(
        "--permission-mode"
    )
    assert invocation.cwd == tmp_path
    # An "official login" preset writes no layer: the CLI keeps the user's own.
    assert invocation.settings_path is None
    assert invocation.env == {}


def test_a_provider_writes_a_claude_settings_layer(isolated_paths, tmp_path):
    agent = ca.normalize_coding_agents(
        [
            _agent(
                providers=[
                    {
                        "id": "gw",
                        "base_url": "https://gw.example",
                        "api_key": "sk-1",
                        "model": "sonnet",
                    }
                ],
                active_provider="gw",
            )
        ]
    )[0]
    invocation = ca.build_invocation(agent, workspace=tmp_path)
    assert invocation.settings_path is not None
    written = invocation.settings_path.read_text(encoding="utf-8")
    assert json.loads(written)["env"] == {
        "ANTHROPIC_BASE_URL": "https://gw.example",
        "ANTHROPIC_MODEL": "sonnet",
    }
    # The endpoint and the model are configuration; the credential is a secret
    # and travels in the child's environment instead of outliving the run.
    assert "sk-1" not in written
    assert invocation.env["ANTHROPIC_BASE_URL"] == "https://gw.example"
    assert invocation.env["ANTHROPIC_AUTH_TOKEN"] == "sk-1"
    assert invocation.argv[invocation.argv.index("--settings") + 1] == str(
        invocation.settings_path
    )


def test_a_provider_without_a_key_keeps_the_user_login(isolated_paths, tmp_path):
    agent = ca.normalize_coding_agents(
        [
            _agent(
                providers=[{"id": "proxy", "base_url": "https://proxy.example"}],
                active_provider="proxy",
            )
        ]
    )[0]
    invocation = ca.build_invocation(agent, workspace=tmp_path)
    assert invocation.settings_path is not None
    payload = json.loads(invocation.settings_path.read_text(encoding="utf-8"))
    assert payload["env"] == {"ANTHROPIC_BASE_URL": "https://proxy.example"}
    assert "ANTHROPIC_AUTH_TOKEN" not in invocation.env


def test_a_codex_invocation_layers_a_profile_file(isolated_paths, tmp_path):
    agent = ca.normalize_coding_agents(
        [
            {
                "id": "codex",
                "type": "codex",
                "enabled": True,
                "command": "codex",
                "project_dir": str(tmp_path / "project"),
                "providers": [
                    {
                        "id": "gw",
                        "name": "Gateway",
                        "base_url": "https://gw.example/v1",
                        "api_key": "sk-2",
                        "model": "gpt-5-codex",
                        "wire_api": "chat",
                    }
                ],
                "active_provider": "gw",
            }
        ]
    )[0]
    invocation = ca.build_invocation(agent, workspace=tmp_path)
    assert invocation.argv[:4] == ("codex", "exec", "--json", "--cd")
    assert "--skip-git-repo-check" in invocation.argv
    assert invocation.argv[invocation.argv.index("-o") + 1] == str(
        tmp_path / ca.LAST_MESSAGE_NAME
    )
    # The layer is named for the agent: two agents running at once each need
    # their own file, because a run would otherwise overwrite the other's.
    assert invocation.argv[invocation.argv.index("--profile") + 1] == (
        ca.codex_profile_name(agent)
    )
    assert ca.codex_profile_name(agent) == f"{ca.CODEX_PROFILE_NAME}-codex"
    assert invocation.env[ca.codex_credential_env_name(agent)] == "sk-2"
    assert invocation.settings_path == ca.codex_profile_path(agent)
    assert invocation.settings_path == Path(isolated_paths) / "codex" / (
        f"{ca.CODEX_PROFILE_NAME}-codex.config.toml"
    )
    written = invocation.settings_path.read_text(encoding="utf-8")
    assert f'model_provider = "{ca.CODEX_PROVIDER_ID}"' in written
    assert f"[model_providers.{ca.CODEX_PROVIDER_ID}]" in written
    assert 'base_url = "https://gw.example/v1"' in written
    assert 'wire_api = "chat"' in written
    assert 'model = "gpt-5-codex"' in written
    # The credential is named, never written.
    assert "sk-2" not in written


def test_a_codex_run_without_a_provider_writes_no_profile(isolated_paths, tmp_path):
    agent = ca.normalize_coding_agents(
        [{"id": "codex", "type": "codex", "enabled": True, "command": "codex"}]
    )[0]
    invocation = ca.build_invocation(agent, workspace=tmp_path)
    assert invocation.settings_path is None
    assert "--profile" not in invocation.argv
    assert not (Path(isolated_paths) / "codex").exists()


def test_a_codex_provider_with_only_a_model_still_writes_a_profile(
    isolated_paths, tmp_path
):
    agent = ca.normalize_coding_agents(
        [
            {
                "id": "codex",
                "type": "codex",
                "enabled": True,
                "command": "codex",
                "providers": [{"id": "local", "model": "o3"}],
                "active_provider": "local",
            }
        ]
    )[0]
    invocation = ca.build_invocation(agent, workspace=tmp_path)
    assert invocation.settings_path is not None
    assert 'model = "o3"' in invocation.settings_path.read_text(encoding="utf-8")


def test_a_custom_agent_runs_its_own_command_line(isolated_paths, tmp_path):
    agent = ca.normalize_coding_agents(
        [
            {
                "id": "other",
                "type": "custom",
                "enabled": True,
                "command": "other-cli",
                "extra_args": ["--print"],
                "env": {"OTHER_TOKEN": "t"},
                "providers": [{"id": "gw", "base_url": "https://gw.example"}],
                "active_provider": "gw",
            }
        ]
    )[0]
    invocation = ca.build_invocation(agent, workspace=tmp_path)
    assert invocation.argv == ("other-cli", "--print")
    assert invocation.env == {"OTHER_TOKEN": "t"}
    # An unknown CLI gets no file it would not read and no env name it never
    # defined; it states its own credentials through `env`.
    assert invocation.settings_path is None
    assert not ca.settings_home(agent).exists()


def test_the_claude_result_line_is_read_from_the_stream():
    stdout = "\n".join(
        [
            "not json",
            '{"type": "system"}',
            '{"type": "result", "result": "first"}',
            "[1, 2]",
            '{"type": "result", "result": "final answer"}',
            '{"type": "result", "result": "   "}',
        ]
    )
    assert ca.agent_result_text({"type": "claude_code"}, stdout) == "final answer"


def test_an_erroring_claude_result_is_logged_and_still_reported(caplog):
    with caplog.at_level("WARNING"):
        text = ca.agent_result_text(
            {"type": "claude_code"},
            '{"type": "result", "is_error": true, "result": "boom"}',
        )
    assert text == "boom"
    assert "error result" in caplog.text


def test_the_codex_result_line_is_read_from_the_stream():
    stdout = "\n".join(
        [
            "not json",
            '{"item": {"type": "reasoning"}}',
            '{"item": {"type": "agent_message", "text": "first"}}',
            '{"item": {"type": "agent_message", "text": "final answer"}}',
            '{"item": {"type": "agent_message", "text": "  "}}',
        ]
    )
    assert ca.agent_result_text({"type": "codex"}, stdout) == "final answer"


def test_the_codex_last_message_file_wins_over_the_stream():
    stdout = '{"item": {"type": "agent_message", "text": "streamed"}}'
    assert ca.agent_result_text({"type": "codex"}, stdout, " written ") == "written"


def test_an_unknown_agent_type_reports_no_message():
    assert ca.agent_result_text({"type": "custom"}, "anything") == ""


def test_truncation_marks_what_it_cut():
    assert ca.truncate_output("short", 10) == "short"
    truncated = ca.truncate_output("abcdefghij", 4)
    assert truncated.startswith("abcd")
    assert "6 characters truncated" in truncated
