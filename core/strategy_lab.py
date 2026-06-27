from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


TRADING_DAYS = 252


@dataclass(frozen=True)
class StrategyDefinition:
    key: str
    name: str
    family: str
    description: str
    requirement: str
    signal_builder: Callable[[pd.DataFrame], pd.Series]


def _close(history: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(history.get("Close"), errors="coerce").dropna()


def _volume(history: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(history.get("Volume"), errors="coerce").reindex(history.index).fillna(0)


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _safe_signal(signal: pd.Series, index: pd.Index) -> pd.Series:
    result = signal.reindex(index).astype(float)
    result = result.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return result.clip(lower=0.0, upper=1.0)


def signal_buy_hold(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    return pd.Series(1.0, index=close.index)


def signal_dca_proxy(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    if close.empty:
        return pd.Series(dtype=float)
    ramp_days = min(len(close), 252)
    values = np.ones(len(close))
    values[:ramp_days] = np.linspace(1 / max(ramp_days, 1), 1, ramp_days)
    return pd.Series(values, index=close.index)


def signal_sma_trend(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    return (sma50 > sma200).astype(float)


def signal_time_series_momentum(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    twelve_month = close.pct_change(252)
    one_month = close.pct_change(21)
    return ((twelve_month - one_month) > 0).astype(float)


def signal_value_proxy(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    sma200 = close.rolling(200).mean()
    discount = (close / sma200) - 1
    return (discount < -0.08).astype(float)


def signal_quality_proxy(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    returns = close.pct_change()
    sma100 = close.rolling(100).mean()
    vol63 = returns.rolling(63).std()
    vol252 = returns.rolling(252).std()
    return ((close > sma100) & (vol63 < vol252)).astype(float)


def signal_low_volatility(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    returns = close.pct_change()
    vol63 = returns.rolling(63).std()
    threshold = vol63.rolling(252).median()
    return (vol63 <= threshold).astype(float)


def signal_mean_reversion_rsi(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    rsi = _rsi(close, 14)
    signal = pd.Series(np.nan, index=close.index)
    signal[rsi < 35] = 1.0
    signal[rsi > 60] = 0.0
    return signal.ffill().fillna(0.0)


def signal_breakout_52w(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    high252 = close.rolling(252).max()
    exit_level = close.rolling(126).min()
    signal = pd.Series(np.nan, index=close.index)
    signal[close >= high252.shift(1)] = 1.0
    signal[close <= exit_level.shift(1)] = 0.0
    return signal.ffill().fillna(0.0)


def signal_volume_momentum(history: pd.DataFrame) -> pd.Series:
    close = _close(history)
    volume = _volume(history).reindex(close.index)
    price_mom = close.pct_change(63)
    volume_ratio = volume / volume.rolling(63).mean()
    return ((price_mom > 0) & (volume_ratio > 1.2)).astype(float)


STRATEGIES: dict[str, StrategyDefinition] = {
    "buy_hold": StrategyDefinition("buy_hold", "Buy & Hold", "Classique", "Acheter le titre et conserver l'exposition pendant toute la période.", "Prix historique.", signal_buy_hold),
    "dca": StrategyDefinition("dca", "Dollar-cost averaging", "Accumulation", "Accumulation progressive de l'exposition sur environ douze mois.", "Prix historique.", signal_dca_proxy),
    "sma_trend": StrategyDefinition("sma_trend", "Tendance SMA 50/200", "Trend following", "Exposition quand la moyenne mobile 50 jours est au-dessus de la 200 jours.", "Au moins 200 séances.", signal_sma_trend),
    "time_series_momentum": StrategyDefinition("time_series_momentum", "Momentum 12-1 mois", "Momentum", "Exposition quand le momentum long terme reste positif hors dernier mois.", "Au moins 252 séances.", signal_time_series_momentum),
    "value_proxy": StrategyDefinition("value_proxy", "Value contrarien proxy", "Value", "Exposition quand le prix est nettement sous sa moyenne 200 jours.", "Proxy prix, pas un vrai ratio fondamental.", signal_value_proxy),
    "quality_proxy": StrategyDefinition("quality_proxy", "Qualité défensive proxy", "Qualité", "Exposition quand la tendance est positive et la volatilité récente se calme.", "Proxy technique.", signal_quality_proxy),
    "low_volatility": StrategyDefinition("low_volatility", "Faible volatilité", "Défensif", "Exposition quand la volatilité récente est sous sa médiane historique.", "Prix historique.", signal_low_volatility),
    "mean_reversion_rsi": StrategyDefinition("mean_reversion_rsi", "Retour à la moyenne RSI", "Contrarien", "Entrée après survente RSI, sortie lorsque le RSI se normalise.", "Prix historique.", signal_mean_reversion_rsi),
    "breakout_52w": StrategyDefinition("breakout_52w", "Cassure 52 semaines", "Breakout", "Exposition après nouveau sommet 52 semaines, sortie sous creux 6 mois.", "Au moins 252 séances.", signal_breakout_52w),
    "volume_momentum": StrategyDefinition("volume_momentum", "Momentum prix-volume", "Momentum", "Exposition quand le prix monte avec un volume supérieur à la normale.", "Prix et volume historiques.", signal_volume_momentum),
}


def strategy_options() -> list[str]:
    return list(STRATEGIES)


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return np.nan
    peak = equity.cummax()
    drawdown = equity / peak - 1
    return float(drawdown.min() * 100)


def _cagr(equity: pd.Series) -> float:
    if equity.empty or len(equity) < 2:
        return np.nan
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 365.25)
    start = float(equity.iloc[0])
    end = float(equity.iloc[-1])
    if start <= 0 or end <= 0:
        return np.nan
    return (end / start) ** (1 / years) - 1


def run_strategy_backtest(
    history: pd.DataFrame,
    strategy_key: str,
    transaction_cost_bps: float = 5.0,
    initial_capital: float = 10_000.0,
) -> dict[str, object]:
    if strategy_key not in STRATEGIES:
        raise KeyError(f"Stratégie inconnue : {strategy_key}")

    close = _close(history)
    if close.empty or len(close) < 30:
        return {"strategy": STRATEGIES[strategy_key], "series": pd.DataFrame(), "metrics": {}, "signals": pd.DataFrame()}

    returns = close.pct_change().fillna(0.0)
    raw_signal = STRATEGIES[strategy_key].signal_builder(history)
    signal = _safe_signal(raw_signal, close.index)

    exposure = signal.shift(1).fillna(0.0)
    turnover = exposure.diff().abs().fillna(exposure.abs())
    cost = turnover * (transaction_cost_bps / 10_000)
    strategy_returns = (exposure * returns) - cost
    benchmark_returns = returns

    strategy_equity = initial_capital * (1 + strategy_returns).cumprod()
    benchmark_equity = initial_capital * (1 + benchmark_returns).cumprod()

    volatility = float(strategy_returns.std() * np.sqrt(TRADING_DAYS))
    sharpe = float((strategy_returns.mean() / strategy_returns.std()) * np.sqrt(TRADING_DAYS)) if strategy_returns.std() else np.nan

    trades = int((turnover > 0).sum())
    invested_pct = float(exposure.mean() * 100)
    total_return = float((strategy_equity.iloc[-1] / strategy_equity.iloc[0] - 1) * 100)
    benchmark_total = float((benchmark_equity.iloc[-1] / benchmark_equity.iloc[0] - 1) * 100)

    metrics = {
        "Rendement total": total_return,
        "Buy & Hold": benchmark_total,
        "CAGR": _cagr(strategy_equity) * 100,
        "Volatilité annualisée": volatility * 100,
        "Sharpe indicatif": sharpe,
        "Drawdown max": _max_drawdown(strategy_equity),
        "Temps investi": invested_pct,
        "Transactions": trades,
    }

    series = pd.DataFrame({
        "Close": close,
        "Signal": signal,
        "Exposition": exposure,
        "Stratégie": strategy_equity,
        "Buy & Hold": benchmark_equity,
        "Rendement stratégie": strategy_returns,
        "Rendement titre": benchmark_returns,
    })

    entries = series[(series["Signal"].diff() > 0) & (series["Signal"] > 0)]
    exits = series[(series["Signal"].diff() < 0) & (series["Signal"] <= 0)]
    signals = pd.concat([entries.assign(Type="Entrée"), exits.assign(Type="Sortie")]).sort_index()

    return {"strategy": STRATEGIES[strategy_key], "series": series, "metrics": metrics, "signals": signals}


def strategy_equity_chart(result: dict[str, object], ticker: str) -> go.Figure:
    series = result.get("series")
    strategy = result.get("strategy")
    if not isinstance(series, pd.DataFrame) or series.empty:
        return go.Figure()
    name = getattr(strategy, "name", "Stratégie")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.72, 0.28])
    fig.add_trace(go.Scatter(x=series.index, y=series["Stratégie"], mode="lines", name=name, line={"width": 2.4}), row=1, col=1)
    fig.add_trace(go.Scatter(x=series.index, y=series["Buy & Hold"], mode="lines", name="Buy & Hold", line={"width": 1.8, "dash": "dash"}), row=1, col=1)
    fig.add_trace(go.Scatter(x=series.index, y=series["Exposition"] * 100, mode="lines", name="Exposition", line={"width": 1.6}, fill="tozeroy"), row=2, col=1)
    fig.update_layout(title=f"Backtest indicatif — {ticker}", template="plotly_white", height=620, margin={"l": 20, "r": 20, "t": 60, "b": 20}, legend={"orientation": "h", "y": 1.04, "x": 0}, hovermode="x unified")
    fig.update_yaxes(title_text="Capital simulé", row=1, col=1)
    fig.update_yaxes(title_text="Exposition %", range=[0, 105], row=2, col=1)
    return fig


def strategy_signal_overlay(history: pd.DataFrame, result: dict[str, object], ticker: str) -> go.Figure:
    close = _close(history)
    signals = result.get("signals")
    strategy = result.get("strategy")
    name = getattr(strategy, "name", "Stratégie")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=close.index, y=close, mode="lines", name=ticker, line={"width": 1.8}))
    if isinstance(signals, pd.DataFrame) and not signals.empty:
        entries = signals[signals["Type"] == "Entrée"]
        exits = signals[signals["Type"] == "Sortie"]
        if not entries.empty:
            fig.add_trace(go.Scatter(x=entries.index, y=entries["Close"], mode="markers", name="Entrées", marker={"symbol": "triangle-up", "size": 11}))
        if not exits.empty:
            fig.add_trace(go.Scatter(x=exits.index, y=exits["Close"], mode="markers", name="Sorties", marker={"symbol": "triangle-down", "size": 11}))
    fig.update_layout(title=f"Signaux — {name}", template="plotly_white", height=420, margin={"l": 20, "r": 20, "t": 60, "b": 20}, legend={"orientation": "h", "y": 1.05, "x": 0}, hovermode="x unified")
    fig.update_yaxes(title_text="Prix")
    return fig


def strategy_catalog_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"Stratégie": strategy.name, "Famille": strategy.family, "Description": strategy.description, "Données requises": strategy.requirement}
        for strategy in STRATEGIES.values()
    ])
