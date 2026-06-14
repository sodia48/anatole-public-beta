from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from core.config import NEGATIVE_NEWS_WORDS, NEWS_CATEGORIES, POSITIVE_NEWS_WORDS
from core.utils import safe_float


def add_indicators(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty or "Close" not in history:
        return pd.DataFrame()
    result = history.copy()
    close = pd.to_numeric(result["Close"], errors="coerce")
    volume = pd.to_numeric(result.get("Volume"), errors="coerce") if "Volume" in result else pd.Series(index=result.index, dtype=float)

    result["SMA20"] = close.rolling(20).mean()
    result["SMA50"] = close.rolling(50).mean()
    result["SMA200"] = close.rolling(200).mean()
    result["EMA20"] = close.ewm(span=20, adjust=False).mean()
    std20 = close.rolling(20).std()
    result["BB_Haut"] = result["SMA20"] + 2 * std20
    result["BB_Bas"] = result["SMA20"] - 2 * std20

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result["RSI14"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    result["MACD"] = ema12 - ema26
    result["SignalMACD"] = result["MACD"].ewm(span=9, adjust=False).mean()
    result["HistogrammeMACD"] = result["MACD"] - result["SignalMACD"]

    result["VolumeMoy20"] = volume.rolling(20).mean()
    result["VolumeRelatif"] = volume / result["VolumeMoy20"].replace(0, np.nan)
    result["Rendement"] = close.pct_change()
    result["Volatilite20"] = result["Rendement"].rolling(20).std() * np.sqrt(252) * 100
    result["PlusHaut52s"] = close.rolling(252, min_periods=50).max()
    result["PlusBas52s"] = close.rolling(252, min_periods=50).min()
    return result


def feature_row(ticker: str, history: pd.DataFrame) -> dict[str, Any]:
    enriched = add_indicators(history)
    if enriched.empty:
        return {"YahooTicker": ticker}
    clean = enriched.dropna(subset=["Close"])
    if clean.empty:
        return {"YahooTicker": ticker}
    last = clean.iloc[-1]
    close = safe_float(last.get("Close"))
    prev = safe_float(clean.iloc[-2].get("Close")) if len(clean) >= 2 else np.nan
    one_month = safe_float(clean.iloc[-22].get("Close")) if len(clean) >= 22 else np.nan
    three_month = safe_float(clean.iloc[-66].get("Close")) if len(clean) >= 66 else np.nan
    one_year = safe_float(clean.iloc[-252].get("Close")) if len(clean) >= 252 else safe_float(clean.iloc[0].get("Close"))
    high52 = safe_float(last.get("PlusHaut52s"))
    low52 = safe_float(last.get("PlusBas52s"))
    return {
        "YahooTicker": ticker,
        "CloseTech": close,
        "DailyChangeTech": ((close / prev) - 1) * 100 if prev else np.nan,
        "Momentum1M": ((close / one_month) - 1) * 100 if one_month else np.nan,
        "Momentum3M": ((close / three_month) - 1) * 100 if three_month else np.nan,
        "Momentum1Y": ((close / one_year) - 1) * 100 if one_year else np.nan,
        "SMA20": safe_float(last.get("SMA20")),
        "SMA50": safe_float(last.get("SMA50")),
        "SMA200": safe_float(last.get("SMA200")),
        "RSI14": safe_float(last.get("RSI14")),
        "MACD": safe_float(last.get("MACD")),
        "SignalMACD": safe_float(last.get("SignalMACD")),
        "VolumeRelatif": safe_float(last.get("VolumeRelatif")),
        "Volatilite20": safe_float(last.get("Volatilite20")),
        "High52": high52,
        "Low52": low52,
        "DistanceHigh52": ((close / high52) - 1) * 100 if high52 else np.nan,
        "DistanceLow52": ((close / low52) - 1) * 100 if low52 else np.nan,
        "AboveSMA20": bool(close > safe_float(last.get("SMA20"))) if not np.isnan(safe_float(last.get("SMA20"))) else False,
        "AboveSMA50": bool(close > safe_float(last.get("SMA50"))) if not np.isnan(safe_float(last.get("SMA50"))) else False,
        "AboveSMA200": bool(close > safe_float(last.get("SMA200"))) if not np.isnan(safe_float(last.get("SMA200"))) else False,
        "GoldenCross": bool(safe_float(last.get("SMA50")) > safe_float(last.get("SMA200"))) if not np.isnan(safe_float(last.get("SMA200"))) else False,
    }


def build_feature_table(
    constituents: pd.DataFrame,
    histories: dict[str, pd.DataFrame],
    snapshot: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows = [feature_row(ticker, histories.get(ticker, pd.DataFrame())) for ticker in constituents["YahooTicker"]]
    features = constituents.merge(pd.DataFrame(rows), on="YahooTicker", how="left")
    if snapshot is not None and not snapshot.empty:
        features = features.merge(snapshot, on="YahooTicker", how="left")
    return features


def market_pulse(features: pd.DataFrame) -> dict[str, Any]:
    if features.empty:
        return {}
    change_col = "Variation" if "Variation" in features else "DailyChangeTech"
    valid = features.dropna(subset=[change_col])
    sector_perf = (
        valid.groupby("Secteur")[change_col].mean().sort_values(ascending=False)
        if not valid.empty and "Secteur" in valid
        else pd.Series(dtype=float)
    )
    new_highs = int((features["DistanceHigh52"] >= -1).sum()) if "DistanceHigh52" in features else 0
    new_lows = int((features["DistanceLow52"] <= 1).sum()) if "DistanceLow52" in features else 0
    weights = pd.to_numeric(valid.get("PoidsIndice"), errors="coerce") if "PoidsIndice" in valid else pd.Series(index=valid.index, dtype=float)
    weighted_change = safe_float((valid[change_col] * weights).sum() / weights.sum()) if not weights.empty and weights.sum() else safe_float(valid[change_col].mean())
    return {
        "average_change": safe_float(valid[change_col].mean()),
        "weighted_change": weighted_change,
        "advancers": int((valid[change_col] > 0).sum()),
        "decliners": int((valid[change_col] < 0).sum()),
        "unchanged": int((valid[change_col] == 0).sum()),
        "above_sma50_pct": safe_float(features["AboveSMA50"].mean() * 100),
        "above_sma200_pct": safe_float(features["AboveSMA200"].mean() * 100),
        "relative_volume": safe_float(features["VolumeRelatif"].replace([np.inf, -np.inf], np.nan).mean()),
        "best_sector": sector_perf.index[0] if not sector_perf.empty else "N/D",
        "best_sector_change": safe_float(sector_perf.iloc[0]) if not sector_perf.empty else np.nan,
        "worst_sector": sector_perf.index[-1] if not sector_perf.empty else "N/D",
        "worst_sector_change": safe_float(sector_perf.iloc[-1]) if not sector_perf.empty else np.nan,
        "new_highs": new_highs,
        "new_lows": new_lows,
        "breadth_ratio": (int((valid[change_col] > 0).sum()) / max(int((valid[change_col] < 0).sum()), 1)),
    }


def technical_signal(row: pd.Series) -> str:
    score = 0
    if bool(row.get("AboveSMA20", False)):
        score += 1
    if bool(row.get("AboveSMA50", False)):
        score += 1
    if bool(row.get("AboveSMA200", False)):
        score += 1
    if safe_float(row.get("MACD")) > safe_float(row.get("SignalMACD")):
        score += 1
    rsi = safe_float(row.get("RSI14"))
    if not np.isnan(rsi):
        if 45 <= rsi <= 70:
            score += 1
        elif rsi < 30:
            score += 0
        elif rsi > 75:
            score -= 1
    if score >= 4:
        return "Haussier"
    if score <= 1:
        return "Baissier"
    return "Neutre"


def apply_screener_preset(df: pd.DataFrame, preset: str) -> pd.DataFrame:
    result = df.copy()
    if preset == "Momentum haussier":
        result = result[(result["AboveSMA20"]) & (result["AboveSMA50"]) & (result["MACD"] > result["SignalMACD"]) & (result["RSI14"].between(50, 75))]
    elif preset == "Actions survendues":
        result = result[result["RSI14"] <= 35]
    elif preset == "Cassures / volume":
        result = result[(result["DistanceHigh52"] >= -3) & (result["VolumeRelatif"] >= 1.5)]
    elif preset == "Tendance long terme":
        result = result[(result["AboveSMA200"]) & (result["GoldenCross"])]
    elif preset == "Dividendes élevés" and "DividendYield" in result:
        result = result[result["DividendYield"] >= 4]
    elif preset == "Valorisation faible" and "PE" in result:
        result = result[(result["PE"] > 0) & (result["PE"] <= 15)]
    return result


def normalize_prices(histories: dict[str, pd.DataFrame]) -> pd.DataFrame:
    series = []
    for ticker, frame in histories.items():
        if frame is None or frame.empty or "Close" not in frame:
            continue
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        if close.empty:
            continue
        close.name = ticker
        series.append(close)
    if not series:
        return pd.DataFrame()
    prices = pd.concat(series, axis=1).dropna(how="all")
    prices = prices.ffill().dropna()
    return prices / prices.iloc[0] * 100


def return_statistics(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    returns = prices.pct_change().dropna()
    rows = []
    for ticker in prices.columns:
        total = prices[ticker].iloc[-1] / prices[ticker].iloc[0] - 1
        years = max((prices.index[-1] - prices.index[0]).days / 365.25, 1 / 252)
        annualized = (1 + total) ** (1 / years) - 1 if total > -1 else -1
        volatility = returns[ticker].std() * np.sqrt(252)
        sharpe = returns[ticker].mean() / returns[ticker].std() * np.sqrt(252) if returns[ticker].std() else np.nan
        wealth = (1 + returns[ticker]).cumprod()
        drawdown = wealth / wealth.cummax() - 1
        rows.append(
            {
                "Ticker": ticker,
                "Rendement total (%)": total * 100,
                "Rendement annualisé (%)": annualized * 100,
                "Volatilité (%)": volatility * 100,
                "Sharpe": sharpe,
                "Drawdown max (%)": drawdown.min() * 100,
            }
        )
    return pd.DataFrame(rows)


def portfolio_table(
    positions: pd.DataFrame,
    quotes: pd.DataFrame,
    constituents: pd.DataFrame,
) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame()
    quote_map = quotes.set_index("YahooTicker").to_dict(orient="index") if not quotes.empty else {}
    sector_map = constituents.set_index("YahooTicker")["Secteur"].to_dict() if not constituents.empty else {}
    rows = []
    for _, row in positions.iterrows():
        ticker = str(row["ticker"]).upper()
        quantity = safe_float(row["quantity"], 0)
        cost = safe_float(row["average_cost"], 0)
        quote = quote_map.get(ticker, {})
        price = safe_float(quote.get("Prix"))
        market_value = quantity * price if not np.isnan(price) else np.nan
        cost_basis = quantity * cost
        pnl = market_value - cost_basis if not np.isnan(market_value) else np.nan
        rows.append(
            {
                "Ticker": ticker,
                "Quantité": quantity,
                "Coût moyen": cost,
                "Prix": price,
                "Valeur": market_value,
                "Coût total": cost_basis,
                "Gain/perte $": pnl,
                "Gain/perte %": (pnl / cost_basis * 100) if cost_basis else np.nan,
                "Variation jour %": safe_float(quote.get("Variation")),
                "Secteur": sector_map.get(ticker, "Autre / hors TSX60"),
                "Notes": row.get("notes", ""),
            }
        )
    result = pd.DataFrame(rows)
    if not result.empty:
        total = result["Valeur"].sum(skipna=True)
        result["Poids %"] = result["Valeur"] / total * 100 if total else np.nan
    return result


def portfolio_risk_metrics(
    positions_table: pd.DataFrame,
    histories: dict[str, pd.DataFrame],
    risk_free_rate: float = 0.03,
) -> dict[str, Any]:
    if positions_table.empty:
        return {}
    prices = []
    weights = {}
    for ticker in positions_table["Ticker"]:
        frame = histories.get(ticker, pd.DataFrame())
        if frame.empty or "Close" not in frame:
            continue
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        close.name = ticker
        prices.append(close)
    if not prices:
        return {}
    matrix = pd.concat(prices, axis=1).ffill().dropna()
    returns = matrix.pct_change().dropna()
    if returns.empty:
        return {}
    value_map = positions_table.set_index("Ticker")["Valeur"].to_dict()
    total_value = sum(safe_float(value_map.get(ticker), 0) for ticker in returns.columns)
    if total_value <= 0:
        equal = 1 / len(returns.columns)
        weights_array = np.array([equal] * len(returns.columns))
    else:
        weights_array = np.array([safe_float(value_map.get(ticker), 0) / total_value for ticker in returns.columns])
    portfolio_returns = returns.mul(weights_array, axis=1).sum(axis=1)
    annual_return = portfolio_returns.mean() * 252
    annual_vol = portfolio_returns.std() * np.sqrt(252)
    sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol else np.nan
    wealth = (1 + portfolio_returns).cumprod()
    drawdown = wealth / wealth.cummax() - 1
    var95 = np.quantile(portfolio_returns, 0.05)

    covariance = returns.cov() * 252
    portfolio_variance = float(weights_array.T @ covariance.values @ weights_array)
    portfolio_sigma = np.sqrt(portfolio_variance) if portfolio_variance > 0 else np.nan
    if not np.isnan(portfolio_sigma) and portfolio_sigma > 0:
        marginal = covariance.values @ weights_array / portfolio_sigma
        component = weights_array * marginal
        contribution_pct = component / portfolio_sigma * 100
    else:
        contribution_pct = np.full(len(weights_array), np.nan)
    risk_contribution = pd.DataFrame({
        "Ticker": returns.columns,
        "Poids %": weights_array * 100,
        "Contribution au risque %": contribution_pct,
    })

    beta = np.nan
    benchmark = histories.get("XIU.TO", pd.DataFrame())
    if not benchmark.empty and "Close" in benchmark:
        benchmark_returns = pd.to_numeric(benchmark["Close"], errors="coerce").pct_change().dropna()
        aligned = pd.concat([portfolio_returns.rename("portfolio"), benchmark_returns.rename("benchmark")], axis=1).dropna()
        if not aligned.empty and aligned["benchmark"].var() > 0:
            beta = aligned["portfolio"].cov(aligned["benchmark"]) / aligned["benchmark"].var()

    return {
        "annual_return": annual_return * 100,
        "annual_volatility": annual_vol * 100,
        "sharpe": sharpe,
        "max_drawdown": drawdown.min() * 100,
        "var95_daily": var95 * 100,
        "equity_curve": wealth,
        "returns": portfolio_returns,
        "correlation": returns.corr(),
        "beta": beta,
        "risk_contribution": risk_contribution,
    }


def score_news_text(title: str, summary: str = "") -> tuple[float, str]:
    text = f"{title} {summary}".lower()
    tokens = set(text.replace("/", " ").replace("-", " ").split())
    positive = sum(1 for word in POSITIVE_NEWS_WORDS if word in text or word in tokens)
    negative = sum(1 for word in NEGATIVE_NEWS_WORDS if word in text or word in tokens)
    denominator = max(positive + negative, 1)
    score = (positive - negative) / denominator
    label = "Positif" if score > 0.2 else "Négatif" if score < -0.2 else "Neutre"
    return score, label


def categorize_news(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    for category, keywords in NEWS_CATEGORIES.items():
        if any(keyword in text for keyword in keywords):
            return category
    return "Autre"


def enrich_news(articles: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    seen: set[str] = set()
    for article in articles:
        title = str(article.get("Titre", "")).strip()
        key = " ".join(title.lower().split())
        if not title or key in seen:
            continue
        seen.add(key)
        score, sentiment = score_news_text(title, str(article.get("Resume", "")))
        rows.append(
            {
                **article,
                "SentimentScore": score,
                "Sentiment": sentiment,
                "Categorie": categorize_news(title, str(article.get("Resume", ""))),
                "Importance": "Élevée" if any(word in title.lower() for word in ["earnings", "results", "acquisition", "lawsuit", "dividend", "résultats", "acquisition", "litige"]) else "Normale",
            }
        )
    result = pd.DataFrame(rows)
    if not result.empty and "Date" in result:
        result["DateParsed"] = pd.to_datetime(result["Date"], errors="coerce", utc=True)
        result = result.sort_values("DateParsed", ascending=False)
    return result


def explain_move(
    row: pd.Series,
    sector_change: float | None,
    news_df: pd.DataFrame | None,
) -> list[str]:
    reasons: list[str] = []
    change = safe_float(row.get("Variation", row.get("DailyChangeTech")))
    rel_volume = safe_float(row.get("VolumeRelatif"))
    rsi = safe_float(row.get("RSI14"))
    distance_high = safe_float(row.get("DistanceHigh52"))
    distance_low = safe_float(row.get("DistanceLow52"))
    sector = safe_float(sector_change)

    if not np.isnan(rel_volume) and rel_volume >= 1.8:
        reasons.append(f"Volume inhabituel : environ {rel_volume:.1f} fois la moyenne sur 20 séances.")
    if not np.isnan(sector) and not np.isnan(change):
        gap = change - sector
        if gap >= 1.5:
            reasons.append(f"Surperformance d'environ {gap:.1f} point par rapport à son secteur.")
        elif gap <= -1.5:
            reasons.append(f"Sous-performance d'environ {abs(gap):.1f} point par rapport à son secteur.")
    if not np.isnan(distance_high) and distance_high >= -2:
        reasons.append("Le cours évolue près de son plus haut sur 52 semaines, ce qui peut signaler une cassure ou un momentum fort.")
    if not np.isnan(distance_low) and distance_low <= 3:
        reasons.append("Le cours évolue près de son plus bas sur 52 semaines, ce qui indique une pression vendeuse ou un rebond spéculatif potentiel.")
    if not np.isnan(rsi):
        if rsi >= 70:
            reasons.append(f"RSI élevé ({rsi:.1f}) : momentum fort, mais risque de surachat.")
        elif rsi <= 30:
            reasons.append(f"RSI faible ({rsi:.1f}) : zone de survente potentielle.")
    if bool(row.get("AboveSMA20", False)) and bool(row.get("AboveSMA50", False)):
        reasons.append("Le cours se maintient au-dessus des moyennes mobiles 20 et 50 jours.")
    if news_df is not None and not news_df.empty:
        recent = news_df.head(5)
        avg_sentiment = safe_float(recent["SentimentScore"].mean())
        if avg_sentiment > 0.2:
            reasons.append("Les manchettes récentes ont un ton globalement positif.")
        elif avg_sentiment < -0.2:
            reasons.append("Les manchettes récentes ont un ton globalement négatif.")
        important = recent[recent["Importance"] == "Élevée"]
        if not important.empty:
            reasons.append(f"Actualité potentiellement importante : {important.iloc[0]['Titre']}")
    if not reasons:
        reasons.append("Aucun facteur dominant n'a été détecté avec les données disponibles; le mouvement peut refléter le marché général, les flux ou une information non captée.")
    return reasons


@dataclass
class BacktestResult:
    frame: pd.DataFrame
    metrics: dict[str, float]
    trades: pd.DataFrame


def run_backtest(
    history: pd.DataFrame,
    strategy: str,
    initial_capital: float = 10_000,
    fee_bps: float = 5,
    rsi_buy: float = 30,
    rsi_sell: float = 70,
) -> BacktestResult:
    data = add_indicators(history).dropna(subset=["Close"]).copy()
    if data.empty:
        return BacktestResult(pd.DataFrame(), {}, pd.DataFrame())

    position = pd.Series(0.0, index=data.index)
    if strategy == "rsi":
        state = 0.0
        values = []
        for _, row in data.iterrows():
            rsi = safe_float(row.get("RSI14"))
            if not np.isnan(rsi):
                if state == 0 and rsi < rsi_buy:
                    state = 1.0
                elif state == 1 and rsi > rsi_sell:
                    state = 0.0
            values.append(state)
        position = pd.Series(values, index=data.index)
    elif strategy == "sma_cross":
        position = (data["SMA20"] > data["SMA50"]).astype(float)
    elif strategy == "price_sma50":
        position = (data["Close"] > data["SMA50"]).astype(float)
    elif strategy == "bollinger":
        state = 0.0
        values = []
        for _, row in data.iterrows():
            close = safe_float(row.get("Close"))
            lower = safe_float(row.get("BB_Bas"))
            upper = safe_float(row.get("BB_Haut"))
            if not np.isnan(lower) and not np.isnan(upper):
                if state == 0 and close < lower:
                    state = 1.0
                elif state == 1 and close > upper:
                    state = 0.0
            values.append(state)
        position = pd.Series(values, index=data.index)
    else:
        position[:] = 1.0

    # Le signal est décalé d'une séance pour éviter d'utiliser une clôture avant qu'elle soit connue.
    data["Position"] = position.shift(1).fillna(0)
    data["AssetReturn"] = data["Close"].pct_change().fillna(0)
    data["Trade"] = data["Position"].diff().abs().fillna(data["Position"])
    fee = fee_bps / 10_000
    data["StrategyReturn"] = data["Position"] * data["AssetReturn"] - data["Trade"] * fee
    data["Equity"] = initial_capital * (1 + data["StrategyReturn"]).cumprod()
    data["BuyHoldEquity"] = initial_capital * (1 + data["AssetReturn"]).cumprod()

    strategy_returns = data["StrategyReturn"]
    total_return = data["Equity"].iloc[-1] / initial_capital - 1
    years = max((data.index[-1] - data.index[0]).days / 365.25, 1 / 252)
    annual_return = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1
    volatility = strategy_returns.std() * np.sqrt(252)
    sharpe = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252) if strategy_returns.std() else np.nan
    drawdown = data["Equity"] / data["Equity"].cummax() - 1

    changes = data[data["Trade"] > 0].copy()
    trades = []
    entry_date = None
    entry_price = None
    for date, row in changes.iterrows():
        if row["Position"] == 1 and entry_date is None:
            entry_date = date
            entry_price = row["Close"]
        elif row["Position"] == 0 and entry_date is not None:
            exit_price = row["Close"]
            trades.append(
                {
                    "Entrée": entry_date,
                    "Sortie": date,
                    "Prix entrée": entry_price,
                    "Prix sortie": exit_price,
                    "Rendement %": (exit_price / entry_price - 1) * 100,
                }
            )
            entry_date = None
            entry_price = None
    trades_df = pd.DataFrame(trades)
    win_rate = float((trades_df["Rendement %"] > 0).mean() * 100) if not trades_df.empty else np.nan
    metrics = {
        "Rendement total (%)": total_return * 100,
        "Rendement annualisé (%)": annual_return * 100,
        "Volatilité annualisée (%)": volatility * 100,
        "Sharpe": sharpe,
        "Drawdown max (%)": drawdown.min() * 100,
        "Transactions": int(data["Trade"].sum()),
        "Taux de réussite (%)": win_rate,
        "Valeur finale": data["Equity"].iloc[-1],
    }
    return BacktestResult(data, metrics, trades_df)


def evaluate_alert(alert: pd.Series | dict[str, Any], feature: pd.Series | dict[str, Any]) -> tuple[bool, float | None, str]:
    alert_type = alert.get("alert_type")
    operator = alert.get("operator")
    threshold = safe_float(alert.get("threshold"))
    ticker = alert.get("ticker", feature.get("YahooTicker", ""))
    mapping = {
        "price": "Prix",
        "daily_change": "Variation",
        "rsi": "RSI14",
        "relative_volume": "VolumeRelatif",
    }
    if alert_type == "sma_cross":
        sma20 = safe_float(feature.get("SMA20"))
        sma50 = safe_float(feature.get("SMA50"))
        value = sma20 - sma50 if not np.isnan(sma20) and not np.isnan(sma50) else np.nan
        previous = safe_float(alert.get("last_value"))
        if operator == "croise_hausse":
            triggered = not np.isnan(previous) and previous <= 0 < value
            message = f"{ticker}: SMA20 vient de croiser SMA50 à la hausse."
        else:
            triggered = not np.isnan(previous) and previous >= 0 > value
            message = f"{ticker}: SMA20 vient de croiser SMA50 à la baisse."
        return triggered, value if not np.isnan(value) else None, message

    column = mapping.get(alert_type)
    value = safe_float(feature.get(column)) if column else np.nan
    if np.isnan(value):
        return False, None, f"{ticker}: donnée indisponible."
    if operator in {">", "au-dessus"}:
        triggered = value > threshold
        condition = f"> {threshold:.2f}"
    elif operator in {"<", "en-dessous"}:
        triggered = value < threshold
        condition = f"< {threshold:.2f}"
    else:
        triggered = False
        condition = str(operator)
    return triggered, value, f"{ticker}: {alert_type} = {value:.2f} ({condition})."
