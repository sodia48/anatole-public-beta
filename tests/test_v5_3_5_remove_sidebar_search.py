from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_search_page_not_registered_in_app_navigation():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "screens/22_Recherche.py" not in app


def test_sidebar_search_removed():
    ui = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert 'render_universal_search("sidebar"' not in ui


def test_home_search_kept():
    page = (ROOT / "screens" / "0_Accueil.py").read_text(encoding="utf-8")
    assert "show_hero_search=True" in page
