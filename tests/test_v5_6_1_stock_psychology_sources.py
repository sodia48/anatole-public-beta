import pandas as pd

from core.analytics import add_indicators
from core.market_psychology import stock_psychology_score, psychology_components_frame


def test_stock_psychology_score_range_and_sources():
    history = pd.DataFrame(
        {
            "Close": [100 + i * 0.2 for i in range(260)],
            "Volume": [1000000 + i * 1000 for i in range(260)],
        }
    )
    history = add_indicators(history)
    market = pd.DataFrame(
        {
            "YahooTicker": ["TEST.TO", "PEER.TO"],
            "Variation": [1.2, 0.4],
            "Secteur": ["Tech", "Tech"],
        }
    )
    result = stock_psychology_score("TEST.TO", history, market, stock_sector="Tech")
    assert 0 <= result["score"] <= 100
    frame = psychology_components_frame(result)
    assert "Source" in frame.columns
    assert "Détail source" in frame.columns
