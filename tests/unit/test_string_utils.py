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
        assert "jinja2" not in source, rel
