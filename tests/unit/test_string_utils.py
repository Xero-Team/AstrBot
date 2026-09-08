import ast
from pathlib import Path

from astrbot.core.utils.string_utils import interpolate_placeholders

ROOT = Path(__file__).resolve().parents[2]
LLM_PLACEHOLDER_MODULES = (
    "astrbot/core/utils/string_utils.py",
    "astrbot/core/astr_main_agent.py",
    "astrbot/core/astr_main_agent_resources.py",
    "astrbot/core/cron/manager.py",
    "astrbot/core/astr_agent_tool_exec.py",
    "astrbot/core/agent/runners/tool_loop_agent_runner.py",
)


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _imports_jinja2(source: str) -> bool:
    return any(
        name == "jinja2" or name.startswith("jinja2.")
        for name in _imported_module_names(source)
    )


def test_interpolate_placeholders_replaces_known_keys():
    assert interpolate_placeholders("X {{a}} Y", {"a": "1"}) == "X 1 Y"


def test_interpolate_placeholders_keeps_unknown_keys_literal():
    assert interpolate_placeholders("{{missing}}", {"a": "1"}) == "{{missing}}"


def test_interpolate_placeholders_does_not_rescan_values():
    assert interpolate_placeholders("{{a}}", {"a": "keep {{a}}"}) == "keep {{a}}"


def test_interpolate_placeholders_replaces_every_occurrence():
    assert interpolate_placeholders("{{a}} {{a}}", {"a": "z"}) == "z z"


def test_interpolate_placeholders_leaves_single_brace_names():
    assert interpolate_placeholders("{a}", {"a": "1"}) == "{a}"


def test_interpolate_placeholders_rejects_inner_whitespace():
    assert interpolate_placeholders("{{ prompt }}", {"prompt": "x"}) == "{{ prompt }}"


def test_interpolate_placeholders_stringifies_values():
    assert interpolate_placeholders("{{n}}", {"n": None}) == ""
    assert interpolate_placeholders("{{n}}", {"n": 3}) == "3"


def test_llm_placeholder_modules_do_not_import_jinja2():
    for rel in LLM_PLACEHOLDER_MODULES:
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert not _imports_jinja2(source), rel


def test_jinja2_import_check_ignores_non_import_mentions():
    assert not _imports_jinja2('"""jinja2"""\n# import jinja2\nvalue = "jinja2"\n')
    assert _imports_jinja2("import jinja2\n")
    assert _imports_jinja2("from jinja2 import Environment\n")
    assert _imports_jinja2("import jinja2.environment\n")
