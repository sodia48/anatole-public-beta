from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v5_modules_exist():
    assert (ROOT / "core" / "device.py").exists()
    assert (ROOT / "core" / "performance.py").exists()
    assert (ROOT / "core" / "data_quality.py").exists()


def test_home_has_professional_cockpit():
    text = (ROOT / "screens" / "0_Accueil.py").read_text(encoding="utf-8")
    assert "Terminal canadien de marché" in text
    assert "sky-home-grid" in text
    assert "render_data_quality_strip" in text


def test_mobile_ui_present():
    text = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert "Mode mobile allégé" in text
    assert "Anatole V5 — mobile first refinements" in text
    assert "sky-mobile-nav" in text


def test_diagnostics_has_data_quality():
    text = (ROOT / "screens" / "10_Diagnostics.py").read_text(encoding="utf-8")
    assert "render_source_status" in text
    assert "render_data_quality_strip" in text
