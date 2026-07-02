from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_news_bundle_has_limits_and_timeout():
    text = (ROOT / "core" / "data.py").read_text(encoding="utf-8")
    assert "ANATOLE_NEWS_MAX_TICKERS" in text
    assert "ANATOLE_NEWS_TIMEOUT" in text
    assert "executor.shutdown(wait=False" in text


def test_actualites_limits_selection():
    text = (ROOT / "screens" / "5_Actualites.py").read_text(encoding="utf-8")
    assert "maximum 6" in text
    assert "max_selections=6" in text
    assert "erreurs 502" in text
