from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_safe_branding_uses_timer_based_patch():
    text = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")

    assert "def force_anatole_browser_brand" in text
    assert "setTimeout(setBrand" in text
    assert "anatole-safe-branding-css" in text
    assert "doc.title = BRAND_TITLE" in text
