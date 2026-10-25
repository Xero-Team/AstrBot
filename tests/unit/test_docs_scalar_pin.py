from pathlib import Path

SCALAR_HTML = Path(__file__).resolve().parents[2] / "docs/public/scalar.html"


def test_scalar_cdn_script_is_versioned_and_integrity_checked():
    html = SCALAR_HTML.read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net/npm/@scalar/api-reference@" in html
    assert '@scalar/api-reference"' not in html
    assert 'integrity="sha384-' in html
    assert 'crossorigin="anonymous"' in html
