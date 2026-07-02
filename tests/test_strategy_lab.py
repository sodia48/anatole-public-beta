import numpy as np
import pandas as pd

from core.strategy_lab import STRATEGIES, run_strategy_backtest, strategy_options


def test_strategy_catalog_has_10_strategies():
    assert len(strategy_options()) == 10
    assert "buy_hold" in STRATEGIES
    assert "sma_trend" in STRATEGIES


def test_strategy_backtest_returns_metrics():
    index = pd.date_range("2020-01-01", periods=320, freq="B")
    close = pd.Series(100 * (1 + np.linspace(0, 0.3, len(index))), index=index)
    history = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1000000}, index=index)
    result = run_strategy_backtest(history, "buy_hold")
    assert result["metrics"]
    assert result["metrics"]["Transactions"] >= 1
    assert not result["series"].empty
