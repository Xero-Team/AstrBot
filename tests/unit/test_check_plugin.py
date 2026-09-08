import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "skills"
    / "create-astrbot-plugin"
    / "scripts"
    / "check_plugin.py"
)
ASTRBOT_ROOT = Path(__file__).resolve().parents[2]
VALID_MAIN = """\
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star


class DemoPlugin(Star):
    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        yield event.plain_result("ok")
"""


def _load():
    spec = importlib.util.spec_from_file_location("check_plugin", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Failed to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_plugin(
    root: Path, name: str, main_py: str, extra: dict[str, str] | None = None
) -> Path:
    plugin = root / name
    plugin.mkdir()
    (plugin / "metadata.yaml").write_text(
        f"name: {name}\ndesc: test\nversion: 0.1.0\nauthor: Test\n",
        encoding="utf-8",
    )
    (plugin / "README.md").write_text(
        "Python requirement: `>=3.14`\n",
        encoding="utf-8",
    )
    (plugin / "main.py").write_text(main_py, encoding="utf-8")
    for relative, content in (extra or {}).items():
        path = plugin / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return plugin


def _run_main(module, plugin: Path, monkeypatch, capsys) -> tuple[int, str]:
    monkeypatch.setattr(
        "sys.argv",
        ["check_plugin.py", "--astrbot-root", str(ASTRBOT_ROOT), str(plugin)],
    )
    code = module.main()
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_rejects_top_level_self_import(tmp_path, monkeypatch, capsys):
    module = _load()
    plugin = _write_plugin(
        tmp_path,
        "demo_plugin",
        "import demo_plugin\n" + VALID_MAIN,
    )
    code, output = _run_main(module, plugin, monkeypatch, capsys)
    assert code == 1
    assert "relative import" in output
    assert "demo_plugin" in output


def test_rejects_from_package_submodule_import(tmp_path, monkeypatch, capsys):
    module = _load()
    plugin = _write_plugin(
        tmp_path,
        "demo_plugin",
        "from demo_plugin.util import helper\n" + VALID_MAIN,
        extra={"util.py": "def helper() -> str:\n    return 'ok'\n"},
    )
    code, output = _run_main(module, plugin, monkeypatch, capsys)
    assert code == 1
    assert "demo_plugin.util" in output


def test_allows_relative_and_public_sdk_imports(tmp_path, monkeypatch, capsys):
    module = _load()
    plugin = _write_plugin(
        tmp_path,
        "demo_plugin",
        "from .util import helper\n" + VALID_MAIN,
        extra={"util.py": "def helper() -> str:\n    return 'ok'\n"},
    )
    code, output = _run_main(module, plugin, monkeypatch, capsys)
    assert code == 0, output
    assert "Plugin contract passed:" in output


def test_relative_import_is_not_treated_as_self_import(tmp_path):
    module = _load()
    path = tmp_path / "main.py"
    path.write_text("from .demo_plugin import helper\n", encoding="utf-8")
    errors: list[str] = []
    module.check_python_file(
        path,
        errors,
        plugin_names=frozenset({"demo_plugin"}),
    )
    assert errors == []


def test_rejects_stacked_filter_command(tmp_path, monkeypatch, capsys):
    module = _load()
    plugin = _write_plugin(
        tmp_path,
        "demo_plugin",
        """\
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star


class DemoPlugin(Star):
    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)

    @filter.command("hello")
    @filter.command("hi")
    async def greet(self, event: AstrMessageEvent):
        yield event.plain_result("ok")
""",
    )
    code, output = _run_main(module, plugin, monkeypatch, capsys)
    assert code == 1
    assert "stacked @filter.command on greet" in output
    assert "command_group" in output


def test_allows_command_with_other_filters(tmp_path, monkeypatch, capsys):
    module = _load()
    plugin = _write_plugin(
        tmp_path,
        "demo_plugin",
        """\
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star


class DemoPlugin(Star):
    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)

    @filter.command("hello")
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def hello(self, event: AstrMessageEvent):
        yield event.plain_result("ok")
""",
    )
    code, output = _run_main(module, plugin, monkeypatch, capsys)
    assert code == 0, output


def test_allows_command_group_subcommand(tmp_path, monkeypatch, capsys):
    module = _load()
    plugin = _write_plugin(
        tmp_path,
        "demo_plugin",
        """\
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star


class DemoPlugin(Star):
    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)

    @filter.command_group("math")
    def math(self):
        pass

    @math.command("add")
    async def add(self, event: AstrMessageEvent, a: int, b: int):
        yield event.plain_result(str(a + b))
""",
    )
    code, output = _run_main(module, plugin, monkeypatch, capsys)
    assert code == 0, output
