import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "docs/scripts/sync_docs_to_wiki.py"


def _module():
    spec = importlib.util.spec_from_file_location("sync_docs_to_wiki", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_paths_are_single_components_under_wiki_root(tmp_path):
    module = _module()
    root = tmp_path / "wiki"
    root.mkdir()
    (root / "safe.md").write_text("ok", encoding="utf-8")
    (root / "nested").mkdir()

    assert module._safe_manifest_path(root, "safe.md") == root / "safe.md"
    for name in (
        "../outside",
        "/etc/passwd",
        "a/b",
        "a\\b",
        ".",
        "..",
        "C:x",
        "nested",
    ):
        assert module._safe_manifest_path(root, name) is None
