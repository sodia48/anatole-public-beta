from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_recent_search_helpers_exist():
    search = (ROOT / "core" / "search.py").read_text(encoding="utf-8")
    assert 'RECENT_SEARCHES_KEY = "_anatole_recent_searches"' in search
    assert "def _register_recent_search" in search
    assert "def render_recent_searches" in search


def test_search_page_mentions_recent_searches():
    page = (ROOT / "screens" / "22_Recherche.py").read_text(encoding="utf-8")
    assert "recherches récentes" in page.lower()
