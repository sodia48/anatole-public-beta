from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ui_forces_anatole_browser_brand():
    text = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")

    assert "def force_anatole_browser_brand" in text
    assert "doc.title = BRAND_TITLE" in text
    assert "short_name: \"Anatole\"" in text
    assert "link.rel = rel" in text
    assert "Anatole — terminal canadien" in text


def test_config_uses_viewer_toolbar():
    text = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")

    assert 'toolbarMode = "viewer"' in text
