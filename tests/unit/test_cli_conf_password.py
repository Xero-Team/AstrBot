from click.testing import CliRunner

from astrbot.cli.commands import cmd_conf


def test_conf_set_password_prompts_hidden(monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(
        cmd_conf,
        "_load_config",
        lambda: {"dashboard": {"password": "old"}},
    )
    monkeypatch.setattr(cmd_conf, "_save_config", lambda config: saved.append(config))

    result = CliRunner().invoke(
        cmd_conf.conf,
        ["set", "dashboard.password"],
        input="NewPassword123\nNewPassword123\n",
    )

    assert result.exit_code == 0, result.output
    assert saved
    assert "NewPassword123" not in result.output


def test_conf_set_password_rejects_plaintext_argument(monkeypatch):
    monkeypatch.setattr(cmd_conf, "_load_config", lambda: {"dashboard": {}})

    result = CliRunner().invoke(
        cmd_conf.conf,
        ["set", "dashboard.password", "PlaintextPassword123"],
    )

    assert result.exit_code == 2
    assert "Refusing a plaintext password argument" in result.output


def test_conf_set_password_reads_stdin_when_requested(monkeypatch):
    saved: list[dict] = []
    monkeypatch.setattr(
        cmd_conf,
        "_load_config",
        lambda: {"dashboard": {"password": "old"}},
    )
    monkeypatch.setattr(cmd_conf, "_save_config", lambda config: saved.append(config))

    result = CliRunner().invoke(
        cmd_conf.conf,
        ["set", "dashboard.password", "-"],
        input="StdinPassword123\n",
    )

    assert result.exit_code == 0, result.output
    assert saved
