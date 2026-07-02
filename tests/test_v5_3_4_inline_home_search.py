from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_enables_hero_search():
    page = (ROOT / 'screens' / '0_Accueil.py').read_text(encoding='utf-8')
    assert 'show_hero_search=True' in page
    assert 'hero_search_profile=profile' in page


def test_hero_search_stays_inline():
    ui = (ROOT / 'core' / 'ui.py').read_text(encoding='utf-8')
    assert "sans quitter l'accueil" in ui
    assert 'navigate_on_select=False' in ui


def test_search_supports_inline_results_mode():
    search = (ROOT / 'core' / 'search.py').read_text(encoding='utf-8')
    assert 'navigate_on_select: bool = True' in search
    assert 'show_inline_results: bool = True' in search
    assert 'st.dataframe(display, hide_index=True, width="stretch")' in search
