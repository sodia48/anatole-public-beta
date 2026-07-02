from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mobile_watchlist_card_helper_exists():
    ui = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert "def render_mobile_watchlist_card" in ui
    assert "sky-mobile-card" in ui


def test_watchlist_uses_mobile_cards():
    watch = (ROOT / "screens" / "9_Watchlist.py").read_text(encoding="utf-8")
    assert "mobile_is_lite()" in watch
    assert "render_mobile_watchlist_card" in watch
    assert "st.switch_page(\"screens/14_Focus.py\")" in watch
