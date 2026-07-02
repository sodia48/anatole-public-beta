from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hero_search_css_escaped_for_fstring():
    ui = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert ".sky-hero-search-card {{" in ui
    assert ".sky-hero-search-title {{" in ui
    assert ".sky-hero-search-note {{" in ui
    assert "margin: -4px 0 18px;" in ui
