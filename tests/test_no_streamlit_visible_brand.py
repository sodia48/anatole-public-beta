from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_no_streamlit_visible_branding_patch_exists():
    text = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")

    assert "def force_anatole_browser_brand" in text
    assert "MutationObserver" in text
    assert "replaceText" in text
    assert "doc.title = BRAND_TITLE" in text
    assert "apple-mobile-web-app-title" in text
    assert "anatole-no-streamlit-branding" in text


def test_streamlit_config_viewer_mode():
    text = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")

    assert 'toolbarMode = "viewer"' in text
    assert 'showErrorDetails = "none"' in text
    assert "gatherUsageStats = false" in text
