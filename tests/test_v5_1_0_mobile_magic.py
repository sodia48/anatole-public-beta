from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mobile_experience_module_exists():
    text = (ROOT / "core" / "mobile_experience.py").read_text(encoding="utf-8")
    assert "def plotly_config" in text
    assert "def install_mobile_viewport_probe" in text
    assert "location.replace" not in text


def test_ui_has_premium_mobile_nav():
    text = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert "Anatole V5.1 — mobile magic polish" in text
    assert "sky-mobile-nav a.active" in text
    assert "install_mobile_viewport_probe" in text
    assert "enforce_same_tab_navigation()" in text


def test_focus_uses_plotly_config_and_lightweight_ownership():
    text = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")
    assert "config=plotly_config()" in text
    assert "info.get(\"heldPercentInstitutions\")" in text
    assert "insider_quick = fetch_insider_activity" not in text


def test_home_no_visible_mobile_v5_block():
    text = (ROOT / "screens" / "0_Accueil.py").read_text(encoding="utf-8")
    assert "Version mobile V5" not in text
