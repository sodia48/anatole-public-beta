from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_uses_hero_search():
    page = (ROOT / "screens" / "0_Accueil.py").read_text(encoding="utf-8")
    assert "show_hero_search=True" in page


def test_ui_contains_hero_search_block():
    ui = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert "Recherche rapide" in ui
    assert "show_hero_search" in ui


def test_search_supports_custom_placeholder():
    search = (ROOT / "core" / "search.py").read_text(encoding="utf-8")
    assert 'placeholder: str = "Rechercher un titre, une page ou une commande…"' in search
