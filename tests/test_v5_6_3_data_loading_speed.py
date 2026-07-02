from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_psychology_page_loads_stock_view_lazily():
    screen = (ROOT / "screens" / "23_Psychologie.py").read_text(encoding="utf-8")
    assert "st.segmented_control" in screen
    assert "st.tabs" not in screen
    assert 'section == "Titre spécifique"' in screen
    assert "include_news = st.toggle" in screen
    assert "if include_news:" in screen


def test_market_snapshot_skips_intraday_for_large_universes_by_default():
    data = (ROOT / "core" / "data.py").read_text(encoding="utf-8")
    assert "def _use_intraday_snapshot" in data
    assert 'ANATOLE_INTRADAY_QUOTES' in data
    assert 'ANATOLE_INTRADAY_MAX_TICKERS' in data
    assert "use_intraday = is_open and _use_intraday_snapshot(len(tickers))" in data
    assert "if use_intraday:" in data