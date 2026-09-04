"""In-app VitePress pages must keep the Dashboard /help/ base."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THEME_DIR = REPO_ROOT / "docs" / ".vitepress" / "theme"


def test_section_tabs_use_with_base() -> None:
    source = (THEME_DIR / "components" / "SectionTabs.vue").read_text(encoding="utf-8")
    assert "withBase" in source
    assert ':href="withBase(tab.link)"' in source
    assert ':href="tab.link"' not in source


def test_not_found_image_uses_with_base() -> None:
    source = (THEME_DIR / "components" / "NotFound.vue").read_text(encoding="utf-8")
    assert "withBase('/404-seio.png')" in source
    assert 'src="/404-seio.png"' not in source


def test_strip_site_base_keeps_help_prefix_out_of_page_path() -> None:
    script = """
import { stripSiteBase, isEnglishDocsPath, isDocsHomePath } from './docs/.vitepress/theme/docsPath.js';
const cases = [
  ['/help/dev/star/plugin-new.html', '/help/', '/dev/star/plugin-new.html'],
  ['/dev/star/plugin-new.html', '/help/', '/dev/star/plugin-new.html'],
  ['/help/', '/help/', '/'],
  ['/help', '/help/', '/'],
  ['/help/en/use/webui.html', '/help/', '/en/use/webui.html'],
  ['/en/use/webui.html', '/', '/en/use/webui.html'],
];
for (const [path, base, expected] of cases) {
  const got = stripSiteBase(path, base);
  if (got !== expected) {
    throw new Error(`${path} + ${base} => ${got}, expected ${expected}`);
  }
}
if (!isEnglishDocsPath('/help/en/use/webui.html', '/help/')) {
  throw new Error('expected English path under /help/');
}
if (isEnglishDocsPath('/help/dev/star/plugin-new.html', '/help/')) {
  throw new Error('did not expect English path for zh page');
}
if (!isDocsHomePath('/help/', '/help/') || !isDocsHomePath('/help/en/', '/help/')) {
  throw new Error('expected docs home paths');
}
"""
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        cwd=REPO_ROOT,
    )
