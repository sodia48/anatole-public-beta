from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_psychology_screen_does_not_import_core_news():
    screen = (ROOT / "screens" / "23_Psychologie.py").read_text(encoding="utf-8")
    assert "from core.news import" not in screen
    assert "core.news" not in screen


def test_psychology_screen_has_news_guard():
    screen = (ROOT / "screens" / "23_Psychologie.py").read_text(encoding="utf-8")
    assert "raw_news = fetch_stock_news(ticker)" in screen
    assert "except Exception:" in screen


def test_psychology_screen_selectbox_has_no_horizontal_argument():
    screen = (ROOT / "screens" / "23_Psychologie.py").read_text(encoding="utf-8")
    assert 'st.selectbox("Historique utilisé", ["6mo", "1y", "2y"], index=1)' in screen
    assert 'selectbox("Historique utilisé", ["6mo", "1y", "2y"], index=1, horizontal=True)' not in screen
