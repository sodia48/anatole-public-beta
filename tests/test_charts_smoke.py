import numpy as np
import pandas as pd

from core.charts import (
    correlation_chart,
    equity_curve_chart,
    heatmap_figure,
    market_breadth_chart,
    normalized_performance_chart,
    oscillator_chart,
    portfolio_allocation_chart,
    price_chart,
    rolling_correlation_chart,
    sector_performance_chart,
)


def _history() -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=260, freq="B")
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0.05, 1, len(index)))
    frame = pd.DataFrame(
        {
            "Open": close + rng.normal(0, 0.25, len(index)),
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": rng.integers(100_000, 2_000_000, len(index)),
        },
        index=index,
    )
    frame["SMA20"] = frame["Close"].rolling(20).mean()
    frame["SMA50"] = frame["Close"].rolling(50).mean()
    frame["SMA200"] = frame["Close"].rolling(200).mean()
    frame["EMA20"] = frame["Close"].ewm(span=20).mean()
    std = frame["Close"].rolling(20).std()
    frame["BB_Haut"] = frame["SMA20"] + 2 * std
    frame["BB_Bas"] = frame["SMA20"] - 2 * std
    frame["RSI14"] = 50.0
    frame["MACD"] = 1.0
    frame["SignalMACD"] = 0.8
    frame["HistogrammeMACD"] = 0.2
    return frame


def test_all_plotly_figures_serialize():
    history = _history()
    market = pd.DataFrame(
        {
            "Ticker": ["RY", "SHOP", "CNQ"],
            "YahooTicker": ["RY.TO", "SHOP.TO", "CNQ.TO"],
            "Nom": ["Royal Bank", "Shopify", "Canadian Natural"],
            "Secteur": ["Financials", "Information Technology", "Energy"],
            "PoidsIndice": [10.0, 8.0, 7.0],
            "Prix": [200.0, 150.0, 50.0],
            "Variation": [1.0, -0.5, 0.3],
            "Volume": [1_000_000, 2_000_000, 800_000],
            "SourceCours": ["Test"] * 3,
            "AboveSMA20": [True, False, True],
            "AboveSMA50": [True, False, True],
            "AboveSMA200": [True, False, False],
        }
    )
    prices = pd.DataFrame(
        {
            "RY.TO": history["Close"],
            "SHOP.TO": history["Close"] * 1.05,
        }
    )

    figures = [
        heatmap_figure(market),
        price_chart(
            history,
            "RY.TO",
            ["SMA 20", "SMA 50", "Bandes de Bollinger"],
        ),
        oscillator_chart(history, "RY.TO"),
        normalized_performance_chart(prices / prices.iloc[0] * 100),
        correlation_chart(prices.pct_change().dropna().corr()),
        portfolio_allocation_chart(
            pd.DataFrame(
                {"Ticker": ["RY.TO", "SHOP.TO"], "Valeur": [1000, 800]}
            )
        ),
        equity_curve_chart(
            pd.DataFrame(
                {
                    "Equity": history["Close"],
                    "BuyHoldEquity": history["Close"] * 1.01,
                }
            )
        ),
        market_breadth_chart(market),
        sector_performance_chart(market),
        rolling_correlation_chart(prices, "RY.TO", "SHOP.TO", 20),
    ]

    for figure in figures:
        payload = figure.to_json()
        assert payload.startswith("{")
        assert '"data"' in payload
