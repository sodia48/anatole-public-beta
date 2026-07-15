from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


def _money(value: Any, currency: str = "CAD") -> str:
    number = _num(value)
    if np.isnan(number):
        return "N/D"
    symbol = "$" if currency in {"CAD", "USD"} else f"{currency} "
    return f"{symbol}{number:,.2f}"


def _pct(value: Any, decimals: int = 2) -> str:
    number = _num(value)
    if np.isnan(number):
        return "N/D"
    return f"{number:+.{decimals}f}%"


def _ratio(value: Any, decimals: int = 2) -> str:
    number = _num(value)
    if np.isnan(number):
        return "N/D"
    return f"{number:.{decimals}f}x"


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame is None or frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def compute_atr(history: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range, robust when OHLC columns are partial."""
    if history is None or history.empty:
        return pd.Series(dtype=float)
    high = pd.to_numeric(history.get("High"), errors="coerce")
    low = pd.to_numeric(history.get("Low"), errors="coerce")
    close = pd.to_numeric(history.get("Close"), errors="coerce")
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=max(3, window // 2)).mean()


def realized_volatility(history: pd.DataFrame, window: int = 20) -> float:
    close = _series(history, "Close")
    if close.size < max(5, window // 2):
        return np.nan
    returns = close.pct_change().dropna().tail(window)
    if returns.empty:
        return np.nan
    return float(returns.std() * np.sqrt(252) * 100)


def max_drawdown(history: pd.DataFrame) -> float:
    close = _series(history, "Close")
    if close.empty:
        return np.nan
    peak = close.cummax()
    dd = close / peak - 1.0
    return float(dd.min() * 100)


def period_return(history: pd.DataFrame) -> float:
    close = _series(history, "Close")
    if close.size < 2 or close.iloc[0] == 0:
        return np.nan
    return float((close.iloc[-1] / close.iloc[0] - 1.0) * 100)


def relative_volume(history: pd.DataFrame, window: int = 20) -> float:
    volume = _series(history, "Volume")
    if volume.size < 2:
        return np.nan
    base = float(volume.tail(window + 1).iloc[:-1].mean()) if volume.size > window else float(volume.iloc[:-1].mean())
    if not np.isfinite(base) or base <= 0:
        return np.nan
    return float(volume.iloc[-1] / base)


def support_resistance(history: pd.DataFrame, price: float, max_levels: int = 3) -> tuple[list[float], list[float]]:
    """Find pragmatic support/resistance zones from recent pivots and quantiles."""
    close = _series(history, "Close")
    high = _series(history, "High")
    low = _series(history, "Low")
    if close.empty or np.isnan(price):
        return [], []

    recent_high = high.tail(90) if not high.empty else close.tail(90)
    recent_low = low.tail(90) if not low.empty else close.tail(90)
    candidates = []
    for series in (recent_high, recent_low, close.tail(120)):
        if series.empty:
            continue
        for q in (0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9):
            value = _num(series.quantile(q))
            if np.isfinite(value):
                candidates.append(value)
        for value in [series.min(), series.max(), series.tail(20).min(), series.tail(20).max()]:
            value = _num(value)
            if np.isfinite(value):
                candidates.append(value)

    # Round by price scale and deduplicate nearby zones.
    rounded = []
    for value in sorted(candidates):
        if value <= 0:
            continue
        precision = 2 if value >= 5 else 3
        value = round(float(value), precision)
        if not rounded or abs(value - rounded[-1]) / max(price, 1.0) > 0.0075:
            rounded.append(value)

    supports = sorted([x for x in rounded if x < price], reverse=True)[:max_levels]
    resistances = sorted([x for x in rounded if x > price])[:max_levels]
    return supports, resistances


def _distance_pct(level: float, price: float) -> float:
    if not price or np.isnan(price) or np.isnan(level):
        return np.nan
    return (level / price - 1.0) * 100


def trading_regime(history: pd.DataFrame) -> dict[str, Any]:
    if history is None or history.empty:
        return {"regime": "Données insuffisantes", "score": 0, "bias": "Neutre", "notes": []}
    last = history.iloc[-1]
    close = _num(last.get("Close"))
    rsi = _num(last.get("RSI14"))
    macd = _num(last.get("MACD"))
    signal = _num(last.get("SignalMACD"))
    sma20 = _num(last.get("SMA20"))
    sma50 = _num(last.get("SMA50"))
    sma200 = _num(last.get("SMA200"))
    atr = _num(compute_atr(history).iloc[-1] if not compute_atr(history).empty else np.nan)
    rv = relative_volume(history)

    score = 50
    notes: list[str] = []
    if np.isfinite(close) and np.isfinite(sma20):
        score += 8 if close >= sma20 else -8
        notes.append("Prix au-dessus de SMA20" if close >= sma20 else "Prix sous SMA20")
    if np.isfinite(close) and np.isfinite(sma50):
        score += 10 if close >= sma50 else -10
        notes.append("Prix au-dessus de SMA50" if close >= sma50 else "Prix sous SMA50")
    if np.isfinite(close) and np.isfinite(sma200):
        score += 12 if close >= sma200 else -12
        notes.append("Prix au-dessus de SMA200" if close >= sma200 else "Prix sous SMA200")
    if np.isfinite(sma20) and np.isfinite(sma50):
        score += 6 if sma20 >= sma50 else -6
    if np.isfinite(sma50) and np.isfinite(sma200):
        score += 6 if sma50 >= sma200 else -6
    if np.isfinite(rsi):
        if 50 <= rsi <= 68:
            score += 8
            notes.append("RSI constructif sans excès majeur")
        elif rsi >= 75:
            score -= 5
            notes.append("RSI très élevé : risque de poursuite tardive")
        elif rsi <= 35:
            score -= 8
            notes.append("RSI faible : pression vendeuse persistante")
    if np.isfinite(macd) and np.isfinite(signal):
        score += 7 if macd >= signal else -7
        notes.append("MACD au-dessus du signal" if macd >= signal else "MACD sous le signal")
    if np.isfinite(rv):
        if rv >= 1.5:
            score += 6
            notes.append("Volume supérieur à la normale")
        elif rv < 0.65:
            score -= 2
            notes.append("Volume faible : conviction limitée")
    if np.isfinite(atr) and np.isfinite(close) and close:
        atr_pct = atr / close * 100
        if atr_pct > 5:
            score -= 5
            notes.append("Volatilité élevée : taille de position à réduire")

    score = int(max(0, min(100, round(score))))
    if score >= 72:
        regime = "Momentum haussier confirmé"
        bias = "Constructif"
    elif score >= 58:
        regime = "Biais positif mais sélectif"
        bias = "Constructif prudent"
    elif score >= 43:
        regime = "Neutre / consolidation"
        bias = "Neutre"
    elif score >= 28:
        regime = "Pression vendeuse contrôlée"
        bias = "Prudent"
    else:
        regime = "Risque baissier élevé"
        bias = "Défensif"
    return {"regime": regime, "score": score, "bias": bias, "notes": notes[:6]}


def trader_levels_table(history: pd.DataFrame, currency: str = "CAD") -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame(columns=["Zone", "Prix", "Distance", "Lecture"])
    last = history.iloc[-1]
    price = _num(last.get("Close"))
    atr_series = compute_atr(history)
    atr = _num(atr_series.iloc[-1] if not atr_series.empty else np.nan)
    supports, resistances = support_resistance(history, price)

    rows: list[dict[str, str]] = []
    for index, level in enumerate(resistances, 1):
        rows.append(
            {
                "Zone": f"Résistance {index}",
                "Prix": _money(level, currency),
                "Distance": _pct(_distance_pct(level, price)),
                "Lecture": "Zone de prise de profit / cassure à confirmer",
            }
        )
    rows.append(
        {
            "Zone": "Prix actuel",
            "Prix": _money(price, currency),
            "Distance": "0,00%",
            "Lecture": "Point de référence",
        }
    )
    for index, level in enumerate(supports, 1):
        rows.append(
            {
                "Zone": f"Support {index}",
                "Prix": _money(level, currency),
                "Distance": _pct(_distance_pct(level, price)),
                "Lecture": "Zone d'invalidation / réaction à surveiller",
            }
        )
    if np.isfinite(atr):
        rows.append(
            {
                "Zone": "ATR 14",
                "Prix": _money(atr, currency),
                "Distance": _pct(atr / price * 100 if price else np.nan),
                "Lecture": "Amplitude moyenne utile pour stops et tailles de position",
            }
        )
    return pd.DataFrame(rows)


def trade_plan(history: pd.DataFrame, currency: str = "CAD", style: str = "Swing") -> dict[str, Any]:
    if history is None or history.empty:
        return {}
    last = history.iloc[-1]
    price = _num(last.get("Close"))
    atr_series = compute_atr(history)
    atr = _num(atr_series.iloc[-1] if not atr_series.empty else np.nan)
    supports, resistances = support_resistance(history, price)
    atr = atr if np.isfinite(atr) and atr > 0 else abs(price) * 0.025
    style_factor = {"Court terme": 0.85, "Swing": 1.25, "Position": 1.85}.get(style, 1.25)
    stop_by_atr = price - atr * style_factor
    stop_by_support = supports[0] * 0.992 if supports else stop_by_atr
    stop = min(stop_by_atr, stop_by_support) if price >= stop_by_support else stop_by_atr
    risk_per_share = max(price - stop, 0)
    target1 = resistances[0] if resistances else price + risk_per_share * 1.6
    target2 = resistances[1] if len(resistances) > 1 else price + risk_per_share * 2.4
    target3 = resistances[2] if len(resistances) > 2 else price + risk_per_share * 3.2

    def rr(target: float) -> float:
        return np.nan if risk_per_share <= 0 else (target - price) / risk_per_share

    return {
        "entry": price,
        "stop": stop,
        "risk_per_share": risk_per_share,
        "atr": atr,
        "target1": target1,
        "target2": target2,
        "target3": target3,
        "rr1": rr(target1),
        "rr2": rr(target2),
        "rr3": rr(target3),
        "currency": currency,
        "style": style,
    }


def position_sizing_table(plan: dict[str, Any], account_size: float, risk_pct: float) -> pd.DataFrame:
    entry = _num(plan.get("entry"))
    stop = _num(plan.get("stop"))
    risk_per_share = _num(plan.get("risk_per_share"))
    risk_budget = account_size * risk_pct / 100.0
    if not np.isfinite(entry) or not np.isfinite(risk_per_share) or risk_per_share <= 0:
        shares = 0
        exposure = np.nan
    else:
        shares = int(max(0, np.floor(risk_budget / risk_per_share)))
        exposure = shares * entry
    rows = [
        {"Mesure": "Capital simulé", "Valeur": f"${account_size:,.2f}"},
        {"Mesure": "Risque maximal choisi", "Valeur": f"{risk_pct:.2f}%"},
        {"Mesure": "Perte maximale théorique", "Valeur": f"${risk_budget:,.2f}"},
        {"Mesure": "Entrée indicative", "Valeur": _money(entry, plan.get("currency", "CAD"))},
        {"Mesure": "Invalidation indicative", "Valeur": _money(stop, plan.get("currency", "CAD"))},
        {"Mesure": "Risque par action", "Valeur": _money(risk_per_share, plan.get("currency", "CAD"))},
        {"Mesure": "Taille théorique", "Valeur": f"{shares:,} action(s)"},
        {"Mesure": "Exposition théorique", "Valeur": "N/D" if not np.isfinite(exposure) else f"${exposure:,.2f}"},
    ]
    return pd.DataFrame(rows)


def scenario_table(plan: dict[str, Any]) -> pd.DataFrame:
    currency = str(plan.get("currency", "CAD"))
    return pd.DataFrame(
        [
            {
                "Scénario": "Cassure confirmée",
                "Zone clé": _money(plan.get("target1"), currency),
                "Ratio R/R": _ratio(plan.get("rr1")),
                "Lecture": "Le prix franchit la première résistance avec volume; attendre confirmation plutôt que poursuivre à l'aveugle.",
            },
            {
                "Scénario": "Continuation propre",
                "Zone clé": _money(plan.get("target2"), currency),
                "Ratio R/R": _ratio(plan.get("rr2")),
                "Lecture": "Le mouvement se prolonge; surveiller volume, RSI et maintien au-dessus des moyennes courtes.",
            },
            {
                "Scénario": "Échec / invalidation",
                "Zone clé": _money(plan.get("stop"), currency),
                "Ratio R/R": "-1.00x",
                "Lecture": "Le plan n'est plus valide sous l'invalidation; éviter de transformer un trade en thèse longue durée.",
            },
        ]
    )


def trader_checklist(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame(columns=["Point de contrôle", "État", "Pourquoi c'est important"])
    last = history.iloc[-1]
    price = _num(last.get("Close"))
    rsi = _num(last.get("RSI14"))
    macd = _num(last.get("MACD"))
    signal = _num(last.get("SignalMACD"))
    sma20 = _num(last.get("SMA20"))
    sma50 = _num(last.get("SMA50"))
    sma200 = _num(last.get("SMA200"))
    rv = relative_volume(history)
    vol = realized_volatility(history)
    rows = []
    checks = [
        ("Tendance courte", price >= sma20 if np.isfinite(price) and np.isfinite(sma20) else None, "Évite d'acheter contre le flux immédiat."),
        ("Tendance moyenne", price >= sma50 if np.isfinite(price) and np.isfinite(sma50) else None, "Confirme si le titre est soutenu par le marché."),
        ("Tendance longue", price >= sma200 if np.isfinite(price) and np.isfinite(sma200) else None, "Sépare rebond tactique et tendance de fond."),
        ("Momentum MACD", macd >= signal if np.isfinite(macd) and np.isfinite(signal) else None, "Détecte l'amélioration ou la détérioration du momentum."),
        ("RSI exploitable", 35 <= rsi <= 72 if np.isfinite(rsi) else None, "Évite les entrées trop tardives ou trop faibles."),
        ("Volume crédible", rv >= 0.9 if np.isfinite(rv) else None, "Un signal sans volume est moins robuste."),
        ("Volatilité maîtrisable", vol <= 45 if np.isfinite(vol) else None, "Réduit le risque d'exécution et de stop trop large."),
    ]
    for label, ok, why in checks:
        if ok is True:
            state = "OK"
        elif ok is False:
            state = "À surveiller"
        else:
            state = "N/D"
        rows.append({"Point de contrôle": label, "État": state, "Pourquoi c'est important": why})
    return pd.DataFrame(rows)


def build_trader_dashboard(history: pd.DataFrame, info: dict[str, Any] | None = None, currency: str = "CAD") -> dict[str, Any]:
    info = info or {}
    if history is None or history.empty:
        return {
            "regime": "Données insuffisantes",
            "score": 0,
            "metrics": {},
            "notes": ["Historique insuffisant pour produire un tableau de bord trader."],
        }
    last = history.iloc[-1]
    close = _num(last.get("Close"))
    atr_series = compute_atr(history)
    atr = _num(atr_series.iloc[-1] if not atr_series.empty else np.nan)
    rv = relative_volume(history)
    regime = trading_regime(history)
    supports, resistances = support_resistance(history, close)
    return {
        "regime": regime.get("regime"),
        "bias": regime.get("bias"),
        "score": regime.get("score"),
        "notes": regime.get("notes", []),
        "metrics": {
            "Rendement période": _pct(period_return(history)),
            "Volatilité 20j ann.": _pct(realized_volatility(history), 1),
            "Drawdown max": _pct(max_drawdown(history), 1),
            "ATR 14": _money(atr, currency),
            "ATR %": _pct(atr / close * 100 if close else np.nan),
            "Volume relatif": _ratio(rv),
            "Support proche": _money(supports[0], currency) if supports else "N/D",
            "Résistance proche": _money(resistances[0], currency) if resistances else "N/D",
        },
    }


def trader_narrative(name: str, ticker: str, dashboard: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    notes = dashboard.get("notes", []) or []
    score = dashboard.get("score", 0)
    regime = dashboard.get("regime", "N/D")
    currency = plan.get("currency", "CAD")
    entry = _money(plan.get("entry"), currency)
    stop = _money(plan.get("stop"), currency)
    target1 = _money(plan.get("target1"), currency)
    rr1 = _ratio(plan.get("rr1"))
    lines = [
        f"{name} ({ticker}) affiche un régime **{regime}** avec un score trader de **{score}/100**.",
        f"Plan tactique indicatif : référence {entry}, invalidation {stop}, première zone de décision {target1} avec R/R {rr1}.",
    ]
    if notes:
        lines.append("Points observés : " + "; ".join(notes[:4]) + ".")
    lines.append(
        "Lecture Anatole : le but n'est pas de prédire, mais de définir un plan mesurable avec invalidation, taille de position et zones de décision."
    )
    return lines
