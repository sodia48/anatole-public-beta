import pandas as pd

from core.market_psychology import market_psychology_score, psychology_components_frame


def test_market_psychology_score_range():
    data = pd.DataFrame(
        {
            "Variation": [1.2, -0.4, 0.8, 2.0, -1.1],
            "AboveSMA50": [True, False, True, True, False],
            "AboveSMA200": [True, False, True, True, True],
            "VolumeRelatif": [1.2, 0.9, 1.1, 1.5, 0.8],
            "Secteur": ["Finance", "Finance", "Tech", "Tech", "Énergie"],
        }
    )
    result = market_psychology_score(data)
    assert 0 <= result["score"] <= 100
    assert result["label"]


def test_market_psychology_components_frame():
    data = pd.DataFrame({"Variation": [1, -1], "Secteur": ["A", "B"]})
    frame = psychology_components_frame(market_psychology_score(data))
    assert not frame.empty
    assert {"Composante", "Score", "Poids", "Lecture"}.issubset(frame.columns)
