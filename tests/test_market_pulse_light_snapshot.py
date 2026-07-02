import numpy as np
import pandas as pd

from core.analytics import market_pulse


def test_market_pulse_accepts_light_snapshot_without_technical_columns():
    frame = pd.DataFrame(
        {
            "Ticker": ["A", "B", "C"],
            "Secteur": ["Energy", "Energy", "Financials"],
            "Variation": [1.0, -0.5, 0.2],
            "PoidsIndice": [2.0, 1.0, 3.0],
        }
    )

    result = market_pulse(frame)

    assert result["advancers"] == 2
    assert result["decliners"] == 1
    assert result["best_sector"] in {"Energy", "Financials"}
    assert "above_sma50_pct" in result
    assert np.isnan(result["above_sma50_pct"])
