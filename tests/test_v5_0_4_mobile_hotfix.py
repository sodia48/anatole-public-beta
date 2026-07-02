from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_search_page_registered():
    assert (ROOT / "screens" / "22_Recherche.py").exists()
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "screens/22_Recherche.py" in app
    assert 'url_path="recherche"' in app


def test_same_tab_guard_exists():
    ui = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert "def enforce_same_tab_navigation" in ui
    assert "target', '_self'" in ui
    assert "/recherche" in ui


def test_anti_502_limits():
    data = (ROOT / "core" / "data.py").read_text(encoding="utf-8")
    universe = (ROOT / "core" / "universe.py").read_text(encoding="utf-8")
    assert 'ANATOLE_NEWS_WORKERS", "1"' in data
    assert 'ANATOLE_NEWS_TIMEOUT", "12"' in data
    assert '"starter": (100, 50)' in universe
    assert '"starter": (80, 35)' in universe
