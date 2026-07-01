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


def _clip_score(value: float) -> float:
    if np.isnan(value):
        return 50.0
    return float(max(0.0, min(100.0, value)))


def _safe_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _score_breadth(market: pd.DataFrame) -> PsychologyComponent:
    variation = _safe_series(market, "Variation")
    if variation.empty:
        return PsychologyComponent("Largeur du marché", 50.0, 0.24, "Largeur du marché indisponible.")
    advancers = float((variation > 0).mean())
    return PsychologyComponent(
        "Largeur du marché",
        _clip_score(advancers * 100),
        0.24,
        f"{advancers:.0%} des titres suivis sont en hausse.",
    )


def _score_momentum(market: pd.DataFrame) -> PsychologyComponent:
    variation = _safe_series(market, "Variation")
    if variation.empty:
        return PsychologyComponent("Momentum prix", 50.0, 0.18, "Momentum intrajournalier indisponible.")
    avg = float(variation.mean())
    score = 50 + (avg / 2.0) * 50
    return PsychologyComponent(
        "Momentum prix",
        _clip_score(score),
        0.18,
        f"Variation moyenne des titres suivis : {avg:+.2f}%.",
    )


def _score_trend(market: pd.DataFrame) -> PsychologyComponent:
    available = [col for col in ["AboveSMA50", "AboveSMA200"] if col in market]
    if not available:
        return PsychologyComponent("Tendance technique", 50.0, 0.18, "Données SMA indisponibles pour cet univers.")

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
        return PsychologyComponent("Tendance technique", 50.0, 0.18, "Données SMA insuffisantes.")

    return PsychologyComponent("Tendance technique", _clip_score(float(np.mean(scores))), 0.18, " · ".join(details) + ".")


def _score_volume(market: pd.DataFrame) -> PsychologyComponent:
    if "VolumeRelatif" not in market or "Variation" not in market:
        return PsychologyComponent("Conviction volume", 50.0, 0.14, "Volume relatif indisponible.")

    joined = pd.DataFrame({
        "volume": pd.to_numeric(market["VolumeRelatif"], errors="coerce"),
        "variation": pd.to_numeric(market["Variation"], errors="coerce"),
    }).dropna()

    if joined.empty:
        return PsychologyComponent("Conviction volume", 50.0, 0.14, "Volume relatif insuffisant.")

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
    )


def _score_sector_dispersion(market: pd.DataFrame) -> PsychologyComponent:
    if "Secteur" not in market or "Variation" not in market:
        return PsychologyComponent("Stress sectoriel", 50.0, 0.14, "Dispersion sectorielle indisponible.")

    sector = (
        market[["Secteur", "Variation"]]
        .assign(Variation=lambda df: pd.to_numeric(df["Variation"], errors="coerce"))
        .dropna()
        .groupby("Secteur", as_index=False)["Variation"]
        .mean()
    )

    if sector.empty:
        return PsychologyComponent("Stress sectoriel", 50.0, 0.14, "Données sectorielles insuffisantes.")

    dispersion = float(sector["Variation"].std(ddof=0)) if len(sector) > 1 else 0.0
    positive_sectors = float((sector["Variation"] > 0).mean())
    score = (positive_sectors * 75) + max(0, 25 - dispersion * 10)
    return PsychologyComponent(
        "Stress sectoriel",
        _clip_score(score),
        0.14,
        f"{positive_sectors:.0%} des secteurs sont positifs; dispersion : {dispersion:.2f}.",
    )


def _score_downside_pressure(market: pd.DataFrame) -> PsychologyComponent:
    variation = _safe_series(market, "Variation")
    if variation.empty:
        return PsychologyComponent("Pression vendeuse", 50.0, 0.12, "Pression vendeuse indisponible.")

    severe = float((variation <= -2.0).mean())
    moderate = float((variation < 0).mean())
    score = 100 - (severe * 70 + moderate * 30)
    return PsychologyComponent(
        "Pression vendeuse",
        _clip_score(score),
        0.12,
        f"{moderate:.0%} des titres sont négatifs; {severe:.0%} baissent de 2% ou plus.",
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


def market_psychology_score(market: pd.DataFrame) -> dict:
    components = market_psychology_components(market)
    total_weight = sum(item.weight for item in components) or 1.0
    score = sum(item.score * item.weight for item in components) / total_weight
    score = _clip_score(score)

    if score < 20:
        label = "Peur extrême"
        tone = "risk_off"
        interpretation = "Le marché montre une aversion au risque élevée."
    elif score < 40:
        label = "Peur"
        tone = "cautious"
        interpretation = "La psychologie est défensive; les acheteurs restent prudents."
    elif score < 60:
        label = "Neutre"
        tone = "neutral"
        interpretation = "Le marché est partagé, sans excès psychologique clair."
    elif score < 80:
        label = "Appétit pour le risque"
        tone = "constructive"
        interpretation = "La psychologie est constructive; les acheteurs dominent modérément."
    else:
        label = "Euphorie / Greed"
        tone = "risk_on"
        interpretation = "Le marché montre un optimisme élevé; attention au risque d'excès."

    return {
        "score": round(score, 1),
        "label": label,
        "tone": tone,
        "interpretation": interpretation,
        "components": components,
    }


def psychology_gauge_figure(score: float, label: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=float(score),
            number={"suffix": "/100", "font": {"size": 36}},
            title={"text": f"Psychologie du marché · {label}", "font": {"size": 16}},
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
            }
        )
    return pd.DataFrame(rows)


def psychology_summary_text(result: dict) -> str:
    score = float(result.get("score", 50))
    label = str(result.get("label", "Neutre"))
    interpretation = str(result.get("interpretation", "Lecture indisponible."))
    return f"Indice psychologique Anatole : {score:.1f}/100 — {label}. {interpretation}"
