from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go


@dataclass(frozen=True)
class PsychologyComponent:
    name: str
    score: float
    weight: float
    description: str
    source: str = "Donnée Anatole"
    source_detail: str = ""


def _clip_score(value: float) -> float:
    if np.isnan(value):
        return 50.0
    return float(max(0.0, min(100.0, value)))


def _safe_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _latest_number(history: pd.DataFrame, column: str) -> float:
    if history.empty or column not in history:
        return np.nan
    series = pd.to_numeric(history[column], errors="coerce").dropna()
    if series.empty:
        return np.nan
    return float(series.iloc[-1])


def _score_breadth(market: pd.DataFrame) -> PsychologyComponent:
    variation = _safe_series(market, "Variation")
    if variation.empty:
        return PsychologyComponent(
            "Largeur du marché", 50.0, 0.24, "Largeur du marché indisponible.",
            "Snapshot marché Anatole", "Variation par titre de l'univers sélectionné."
        )
    advancers = float((variation > 0).mean())
    return PsychologyComponent(
        "Largeur du marché",
        _clip_score(advancers * 100),
        0.24,
        f"{advancers:.0%} des titres suivis sont en hausse.",
        "Snapshot marché Anatole",
        "Calculé avec la variation des titres de l'univers actif.",
    )


def _score_momentum(market: pd.DataFrame) -> PsychologyComponent:
    variation = _safe_series(market, "Variation")
    if variation.empty:
        return PsychologyComponent(
            "Momentum prix", 50.0, 0.18, "Momentum intrajournalier indisponible.",
            "Snapshot marché Anatole", "Variation moyenne indisponible."
        )
    avg = float(variation.mean())
    score = 50 + (avg / 2.0) * 50
    return PsychologyComponent(
        "Momentum prix",
        _clip_score(score),
        0.18,
        f"Variation moyenne des titres suivis : {avg:+.2f}%.",
        "Snapshot marché Anatole",
        "Prix et variation récupérés via les fournisseurs de données déjà utilisés par Anatole.",
    )


def _score_trend(market: pd.DataFrame) -> PsychologyComponent:
    available = [col for col in ["AboveSMA50", "AboveSMA200"] if col in market]
    if not available:
        return PsychologyComponent(
            "Tendance technique", 50.0, 0.18, "Données SMA indisponibles pour cet univers.",
            "Indicateurs techniques Anatole", "Colonnes AboveSMA50 / AboveSMA200 absentes."
        )

    scores: list[float] = []
    details: list[str] = []
    for col in available:
        series = pd.to_numeric(market[col], errors="coerce").dropna()
        if series.empty:
            continue
        pct = float(series.astype(bool).mean())
        scores.append(pct * 100)
        label = "SMA50" if col == "AboveSMA50" else "SMA200"
        details.append(f"{pct:.0%} au-dessus de {label}")

    if not scores:
        return PsychologyComponent(
            "Tendance technique", 50.0, 0.18, "Données SMA insuffisantes.",
            "Indicateurs techniques Anatole", "Moyennes mobiles calculées localement."
        )

    return PsychologyComponent(
        "Tendance technique", _clip_score(float(np.mean(scores))), 0.18,
        " · ".join(details) + ".",
        "Indicateurs techniques Anatole",
        "Moyennes mobiles calculées à partir de l'historique de prix.",
    )


def _score_volume(market: pd.DataFrame) -> PsychologyComponent:
    if "VolumeRelatif" not in market or "Variation" not in market:
        return PsychologyComponent(
            "Conviction volume", 50.0, 0.14, "Volume relatif indisponible.",
            "Snapshot marché Anatole", "Volume relatif absent de l'univers actif."
        )

    joined = pd.DataFrame({
        "volume": pd.to_numeric(market["VolumeRelatif"], errors="coerce"),
        "variation": pd.to_numeric(market["Variation"], errors="coerce"),
    }).dropna()

    if joined.empty:
        return PsychologyComponent(
            "Conviction volume", 50.0, 0.14, "Volume relatif insuffisant.",
            "Snapshot marché Anatole", "Volume relatif non exploitable."
        )

    up_rows = joined[joined["variation"] > 0]
    down_rows = joined[joined["variation"] < 0]
    up_volume = float(up_rows["volume"].mean()) if not up_rows.empty else 1.0
    down_volume = float(down_rows["volume"].mean()) if not down_rows.empty else 1.0
    ratio = up_volume / max(down_volume, 0.01)
    score = 50 + (ratio - 1.0) * 30
    return PsychologyComponent(
        "Conviction volume",
        _clip_score(score),
        0.14,
        f"Volume moyen titres haussiers : {up_volume:.2f}x vs baissiers : {down_volume:.2f}x.",
        "Volume relatif Anatole",
        "Compare la force du volume sur les titres haussiers et baissiers.",
    )


def _score_sector_dispersion(market: pd.DataFrame) -> PsychologyComponent:
    if "Secteur" not in market or "Variation" not in market:
        return PsychologyComponent(
            "Stress sectoriel", 50.0, 0.14, "Dispersion sectorielle indisponible.",
            "Classification sectorielle Anatole", "Secteur ou variation absent."
        )

    sector = (
        market[["Secteur", "Variation"]]
        .assign(Variation=lambda df: pd.to_numeric(df["Variation"], errors="coerce"))
        .dropna()
        .groupby("Secteur", as_index=False)["Variation"]
        .mean()
    )

    if sector.empty:
        return PsychologyComponent(
            "Stress sectoriel", 50.0, 0.14, "Données sectorielles insuffisantes.",
            "Classification sectorielle Anatole", "Regroupement sectoriel impossible."
        )

    dispersion = float(sector["Variation"].std(ddof=0)) if len(sector) > 1 else 0.0
    positive_sectors = float((sector["Variation"] > 0).mean())
    score = (positive_sectors * 75) + max(0, 25 - dispersion * 10)
    return PsychologyComponent(
        "Stress sectoriel",
        _clip_score(score),
        0.14,
        f"{positive_sectors:.0%} des secteurs sont positifs; dispersion : {dispersion:.2f}.",
        "Classification sectorielle Anatole",
        "Moyenne des variations par secteur dans l'univers actif.",
    )


def _score_downside_pressure(market: pd.DataFrame) -> PsychologyComponent:
    variation = _safe_series(market, "Variation")
    if variation.empty:
        return PsychologyComponent(
            "Pression vendeuse", 50.0, 0.12, "Pression vendeuse indisponible.",
            "Snapshot marché Anatole", "Variation par titre indisponible."
        )

    severe = float((variation <= -2.0).mean())
    moderate = float((variation < 0).mean())
    score = 100 - (severe * 70 + moderate * 30)
    return PsychologyComponent(
        "Pression vendeuse",
        _clip_score(score),
        0.12,
        f"{moderate:.0%} des titres sont négatifs; {severe:.0%} baissent de 2% ou plus.",
        "Snapshot marché Anatole",
        "Mesure la proportion de titres en baisse et en baisse sévère.",
    )


def market_psychology_components(market: pd.DataFrame) -> list[PsychologyComponent]:
    return [
        _score_breadth(market),
        _score_momentum(market),
        _score_trend(market),
        _score_volume(market),
        _score_sector_dispersion(market),
        _score_downside_pressure(market),
    ]


def _label_for_score(score: float) -> tuple[str, str, str]:
    if score < 20:
        return "Peur extrême", "risk_off", "Le marché montre une aversion au risque élevée."
    if score < 40:
        return "Peur", "cautious", "La psychologie est défensive; les acheteurs restent prudents."
    if score < 60:
        return "Neutre", "neutral", "Le marché est partagé, sans excès psychologique clair."
    if score < 80:
        return "Appétit pour le risque", "constructive", "La psychologie est constructive; les acheteurs dominent modérément."
    return "Euphorie / Greed", "risk_on", "Le marché montre un optimisme élevé; attention au risque d'excès."


def _weighted_result(components: list[PsychologyComponent]) -> dict:
    total_weight = sum(item.weight for item in components) or 1.0
    score = sum(item.score * item.weight for item in components) / total_weight
    score = _clip_score(score)
    label, tone, interpretation = _label_for_score(score)
    return {
        "score": round(score, 1),
        "label": label,
        "tone": tone,
        "interpretation": interpretation,
        "components": components,
    }


def market_psychology_score(market: pd.DataFrame) -> dict:
    return _weighted_result(market_psychology_components(market))


def _stock_momentum_component(history: pd.DataFrame) -> PsychologyComponent:
    close = _safe_series(history, "Close")
    if len(close) < 22:
        return PsychologyComponent("Momentum du titre", 50.0, 0.22, "Historique insuffisant.", "Historique prix", "Close.")
    ret_1m = (close.iloc[-1] / close.iloc[-22] - 1) * 100
    score = 50 + (ret_1m / 10.0) * 50
    return PsychologyComponent(
        "Momentum du titre", _clip_score(score), 0.22,
        f"Rendement approximatif 1 mois : {ret_1m:+.2f}%.",
        "Historique prix réel", "Prix de clôture utilisés par Anatole.",
    )


def _stock_trend_component(history: pd.DataFrame) -> PsychologyComponent:
    close = _safe_series(history, "Close")
    if len(close) < 50:
        return PsychologyComponent("Tendance du titre", 50.0, 0.20, "Historique insuffisant pour SMA50.", "Historique prix", "Close.")
    last = close.iloc[-1]
    sma50 = close.tail(50).mean()
    sma200 = close.tail(200).mean() if len(close) >= 200 else np.nan
    points = [last >= sma50]
    details = [f"prix {'au-dessus' if last >= sma50 else 'sous'} SMA50"]
    if not np.isnan(sma200):
        points.append(last >= sma200)
        details.append(f"prix {'au-dessus' if last >= sma200 else 'sous'} SMA200")
    score = 100 * float(np.mean(points))
    return PsychologyComponent(
        "Tendance du titre", _clip_score(score), 0.20,
        " · ".join(details) + ".",
        "Indicateurs techniques réels", "SMA calculées localement sur l'historique de prix.",
    )


def _stock_rsi_component(history: pd.DataFrame) -> PsychologyComponent:
    rsi = _latest_number(history, "RSI14")
    if np.isnan(rsi):
        return PsychologyComponent("RSI / excès", 50.0, 0.14, "RSI indisponible.", "Indicateur technique Anatole", "RSI14.")
    if rsi >= 70:
        score = 85
        desc = f"RSI {rsi:.1f}: optimisme élevé, risque de surachat."
    elif rsi <= 30:
        score = 20
        desc = f"RSI {rsi:.1f}: peur marquée, possible pression vendeuse excessive."
    else:
        score = 50 + (rsi - 50)
        desc = f"RSI {rsi:.1f}: zone intermédiaire."
    return PsychologyComponent("RSI / excès", _clip_score(score), 0.14, desc, "Indicateur technique Anatole", "RSI14 calculé localement.")


def _stock_volume_component(history: pd.DataFrame) -> PsychologyComponent:
    volume = _safe_series(history, "Volume")
    close = _safe_series(history, "Close")
    if len(volume) < 21 or len(close) < 2:
        return PsychologyComponent("Conviction volume", 50.0, 0.14, "Volume insuffisant.", "Historique volume", "Volume.")
    last_volume = volume.iloc[-1]
    avg_volume = volume.tail(20).mean()
    ratio = last_volume / max(avg_volume, 1)
    direction = close.iloc[-1] >= close.iloc[-2]
    score = 50 + (ratio - 1.0) * (22 if direction else -22)
    side = "acheteuse" if direction else "vendeuse"
    return PsychologyComponent(
        "Conviction volume", _clip_score(score), 0.14,
        f"Volume relatif {ratio:.2f}x avec pression {side}.",
        "Historique volume réel", "Volume actuel comparé à la moyenne 20 séances.",
    )


def _stock_range_component(history: pd.DataFrame) -> PsychologyComponent:
    close = _safe_series(history, "Close")
    if len(close) < 60:
        return PsychologyComponent("Position dans le range", 50.0, 0.12, "Historique insuffisant.", "Historique prix", "Close.")
    recent = close.tail(min(252, len(close)))
    low = recent.min()
    high = recent.max()
    if high <= low:
        score = 50.0
    else:
        score = (close.iloc[-1] - low) / (high - low) * 100
    return PsychologyComponent(
        "Position dans le range", _clip_score(score), 0.12,
        f"Position dans le range récent : {score:.0f}/100.",
        "Historique prix réel", "Position du dernier cours entre le creux et le sommet récents.",
    )


def _stock_sector_relative_component(ticker: str, market: pd.DataFrame, stock_sector: str | None = None) -> PsychologyComponent:
    if market.empty or "YahooTicker" not in market or "Variation" not in market:
        return PsychologyComponent("Force relative secteur", 50.0, 0.10, "Comparaison secteur indisponible.", "Snapshot marché Anatole", "Variation intrajournalière.")
    row = market.loc[market["YahooTicker"].astype(str).str.upper() == str(ticker).upper()]
    if row.empty:
        return PsychologyComponent("Force relative secteur", 50.0, 0.10, "Titre absent du snapshot marché.", "Snapshot marché Anatole", "Univers actif.")
    ticker_var = pd.to_numeric(row.iloc[0].get("Variation"), errors="coerce")
    sector = stock_sector or row.iloc[0].get("Secteur")
    if pd.isna(ticker_var) or "Secteur" not in market:
        return PsychologyComponent("Force relative secteur", 50.0, 0.10, "Variation ou secteur indisponible.", "Snapshot marché Anatole", "Variation et secteur.")
    peers = market.loc[market["Secteur"].astype(str) == str(sector)]
    peer_avg = pd.to_numeric(peers["Variation"], errors="coerce").dropna().mean()
    if pd.isna(peer_avg):
        return PsychologyComponent("Force relative secteur", 50.0, 0.10, "Moyenne sectorielle indisponible.", "Snapshot marché Anatole", "Pairs sectoriels.")
    spread = float(ticker_var - peer_avg)
    score = 50 + (spread / 3.0) * 50
    return PsychologyComponent(
        "Force relative secteur", _clip_score(score), 0.10,
        f"Écart au secteur {sector}: {spread:+.2f} point(s).",
        "Snapshot marché Anatole", "Variation du titre comparée à la moyenne de son secteur.",
    )


def _stock_news_component(news: pd.DataFrame | None) -> PsychologyComponent:
    if news is None or news.empty or "SentimentScore" not in news:
        return PsychologyComponent("Sentiment nouvelles", 50.0, 0.08, "Nouvelles/sentiment indisponibles.", "Flux nouvelles Anatole", "Yahoo Finance quand disponible.")
    scores = pd.to_numeric(news["SentimentScore"], errors="coerce").dropna()
    if scores.empty:
        return PsychologyComponent("Sentiment nouvelles", 50.0, 0.08, "Sentiment non exploitable.", "Flux nouvelles Anatole", "SentimentScore.")
    avg = float(scores.head(10).mean())
    score = 50 + avg * 50
    return PsychologyComponent(
        "Sentiment nouvelles", _clip_score(score), 0.08,
        f"Sentiment moyen des nouvelles récentes : {avg:+.2f}.",
        "Flux nouvelles Anatole", "Analyse lexicale interne sur titres/résumés disponibles.",
    )


def stock_psychology_score(
    ticker: str,
    history: pd.DataFrame,
    market: pd.DataFrame,
    news: pd.DataFrame | None = None,
    stock_sector: str | None = None,
) -> dict:
    components = [
        _stock_momentum_component(history),
        _stock_trend_component(history),
        _stock_rsi_component(history),
        _stock_volume_component(history),
        _stock_range_component(history),
        _stock_sector_relative_component(ticker, market, stock_sector),
        _stock_news_component(news),
    ]
    result = _weighted_result(components)
    result["ticker"] = ticker
    return result


def psychology_gauge_figure(score: float, label: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=float(score),
            number={"suffix": "/100", "font": {"size": 36}},
            title={"text": f"Psychologie · {label}", "font": {"size": 16}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"thickness": 0.24},
                "steps": [
                    {"range": [0, 20], "color": "rgba(239,68,68,.22)"},
                    {"range": [20, 40], "color": "rgba(245,158,11,.22)"},
                    {"range": [40, 60], "color": "rgba(148,163,184,.22)"},
                    {"range": [60, 80], "color": "rgba(59,130,246,.22)"},
                    {"range": [80, 100], "color": "rgba(16,185,129,.22)"},
                ],
                "threshold": {"line": {"width": 3}, "thickness": 0.75, "value": float(score)},
            },
        )
    )
    fig.update_layout(
        height=320,
        margin={"l": 24, "r": 24, "t": 48, "b": 18},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, sans-serif"},
    )
    return fig


def psychology_components_frame(result: dict) -> pd.DataFrame:
    rows = []
    for item in result.get("components", []):
        rows.append(
            {
                "Composante": item.name,
                "Score": round(float(item.score), 1),
                "Poids": f"{item.weight:.0%}",
                "Lecture": item.description,
                "Source": item.source,
                "Détail source": item.source_detail,
            }
        )
    return pd.DataFrame(rows)


def psychology_summary_text(result: dict) -> str:
    score = float(result.get("score", 50))
    label = str(result.get("label", "Neutre"))
    interpretation = str(result.get("interpretation", "Lecture indisponible."))
    return f"Indice psychologique Anatole : {score:.1f}/100 — {label}. {interpretation}"
