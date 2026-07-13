from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd


PREFERRED_COLUMNS = [
    "Ticker",
    "YahooTicker",
    "Nom",
    "Secteur",
    "Prix",
    "Variation",
    "RSI14",
    "VolumeRelatif",
    "DividendYield",
    "TrailingPE",
    "ForwardPE",
    "Beta",
    "MarketCap",
    "PoidsIndice",
    "SMA20",
    "SMA50",
    "SMA200",
    "Rendement1M",
    "Rendement3M",
    "Rendement6M",
    "Rendement1Y",
    "SourceCours",
]

NUMERIC_COLUMNS = [
    "Prix",
    "Variation",
    "RSI14",
    "VolumeRelatif",
    "DividendYield",
    "TrailingPE",
    "ForwardPE",
    "Beta",
    "MarketCap",
    "PoidsIndice",
    "SMA20",
    "SMA50",
    "SMA200",
    "Rendement1M",
    "Rendement3M",
    "Rendement6M",
    "Rendement1Y",
]


@dataclass(frozen=True)
class RegimeSnapshot:
    label: str
    tone: str
    breadth: float
    average_change: float
    weighted_change: float
    advancers: int
    decliners: int
    top_sector: str
    bottom_sector: str
    concentration: float
    risk_level: str


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


def _clean_text(value: Any, default: str = "N/D") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return default
    return text


def _pct(value: Any, decimals: int = 2, signed: bool = True) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.{decimals}f} %".replace(".", ",")


def _num(value: Any, decimals: int = 1) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    return f"{number:,.{decimals}f}".replace(",", " ").replace(".", ",")


def _clip_score(value: Any) -> float:
    number = _safe_float(value, 50.0)
    if np.isnan(number):
        return 50.0
    return float(max(0.0, min(100.0, number)))


def _rank_score(series: pd.Series, *, higher_is_better: bool = True, neutral: float = 50.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() < 3:
        return pd.Series(neutral, index=series.index, dtype=float)
    ranked = numeric.rank(pct=True, ascending=not higher_is_better) * 100
    return ranked.fillna(neutral).clip(0, 100)


def _distance_score(price: pd.Series, average: pd.Series) -> pd.Series:
    price = pd.to_numeric(price, errors="coerce")
    average = pd.to_numeric(average, errors="coerce")
    distance = ((price / average) - 1.0) * 100
    score = 50 + distance * 2.0
    return score.replace([np.inf, -np.inf], np.nan).fillna(50).clip(0, 100)


def prepare_market_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Normalise un tableau de marché sans dépendre d'une source externe.

    La fonction est volontairement tolérante : si certaines colonnes manquent,
    elles sont ajoutées à vide afin que les pages avancées ne cassent pas.
    """
    if frame is None or frame.empty:
        return pd.DataFrame(columns=PREFERRED_COLUMNS)

    work = frame.copy()
    if "Ticker" not in work.columns and "YahooTicker" in work.columns:
        work["Ticker"] = work["YahooTicker"].astype(str).str.replace(".TO", "", regex=False)
    if "YahooTicker" not in work.columns and "Ticker" in work.columns:
        work["YahooTicker"] = work["Ticker"].astype(str).map(lambda x: x if x.endswith(".TO") else f"{x}.TO")
    if "Nom" not in work.columns:
        work["Nom"] = work.get("Ticker", pd.Series("N/D", index=work.index))
    if "Secteur" not in work.columns:
        work["Secteur"] = "Autre"

    for column in PREFERRED_COLUMNS:
        if column not in work.columns:
            work[column] = np.nan
    for column in NUMERIC_COLUMNS:
        work[column] = pd.to_numeric(work[column], errors="coerce")

    work["Ticker"] = work["Ticker"].fillna("").astype(str).str.replace(".TO", "", regex=False).str.upper()
    work["YahooTicker"] = work["YahooTicker"].fillna(work["Ticker"]).astype(str)
    work["Nom"] = work["Nom"].fillna(work["Ticker"]).astype(str)
    work["Secteur"] = work["Secteur"].fillna("Autre").astype(str)
    work = work[work["Ticker"].astype(str).str.len() > 0].drop_duplicates(subset=["Ticker"], keep="first")
    return work.reset_index(drop=True)


def score_titles(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Construit une matrice de scores explicable pour chaque titre.

    Le score n'est pas une recommandation. Il sert à prioriser les analyses et
    à faire émerger les titres qui méritent une vérification humaine.
    """
    work = prepare_market_frame(frame)
    if work.empty:
        return work

    variation_score = _rank_score(work["Variation"], higher_is_better=True)
    r1m_score = _rank_score(work["Rendement1M"], higher_is_better=True)
    r3m_score = _rank_score(work["Rendement3M"], higher_is_better=True)
    sma50_score = _distance_score(work["Prix"], work["SMA50"])
    sma200_score = _distance_score(work["Prix"], work["SMA200"])

    # Momentum : séance + tendance courte + tendance longue.
    work["Score momentum"] = (
        variation_score * 0.25
        + r1m_score * 0.20
        + r3m_score * 0.25
        + sma50_score * 0.15
        + sma200_score * 0.15
    ).clip(0, 100)

    rsi = work["RSI14"]
    rsi_balance = (100 - (rsi - 50).abs() * 2).fillna(50).clip(0, 100)
    volume = pd.to_numeric(work["VolumeRelatif"], errors="coerce").fillna(1.0)
    volume_confirmation = (50 + (volume - 1.0) * 25).clip(0, 100)
    work["Score technique"] = (rsi_balance * 0.40 + volume_confirmation * 0.25 + sma50_score * 0.20 + sma200_score * 0.15).clip(0, 100)

    yield_score = _rank_score(work["DividendYield"], higher_is_better=True)
    work["Score revenu"] = yield_score

    pe = work["TrailingPE"].fillna(work["ForwardPE"])
    pe_score = _rank_score(pe.where(pe > 0), higher_is_better=False)
    work["Score valorisation"] = pe_score

    beta = work["Beta"]
    beta_risk = (100 - (beta.fillna(1.0) - 1.0).abs() * 45).clip(0, 100)
    volatility_proxy = (100 - work["Variation"].abs().fillna(0) * 10).clip(0, 100)
    work["Score risque"] = (beta_risk * 0.55 + volatility_proxy * 0.45).clip(0, 100)

    marketcap_score = _rank_score(work["MarketCap"], higher_is_better=True, neutral=55)
    weight_score = _rank_score(work["PoidsIndice"], higher_is_better=True, neutral=55)
    work["Score liquidité"] = (marketcap_score * 0.65 + weight_score * 0.35).clip(0, 100)

    work["Score Anatole"] = (
        work["Score momentum"] * 0.28
        + work["Score technique"] * 0.22
        + work["Score risque"] * 0.18
        + work["Score valorisation"] * 0.14
        + work["Score revenu"] * 0.10
        + work["Score liquidité"] * 0.08
    ).round(1).clip(0, 100)

    work["Catégorie"] = work.apply(_classify_row, axis=1)
    work["Lecture Anatole"] = work.apply(_row_thesis, axis=1)
    work["Points à vérifier"] = work.apply(_row_checks, axis=1)
    work["Risque principal"] = work.apply(_row_risk, axis=1)
    ordered = [
        "Ticker",
        "YahooTicker",
        "Nom",
        "Secteur",
        "Prix",
        "Variation",
        "Score Anatole",
        "Catégorie",
        "Lecture Anatole",
        "Risque principal",
        "Points à vérifier",
        "RSI14",
        "VolumeRelatif",
        "DividendYield",
        "TrailingPE",
        "Score momentum",
        "Score technique",
        "Score risque",
        "Score valorisation",
        "Score revenu",
        "Score liquidité",
    ]
    return work[[c for c in ordered if c in work.columns]].sort_values("Score Anatole", ascending=False).reset_index(drop=True)


def _classify_row(row: pd.Series) -> str:
    score = _safe_float(row.get("Score Anatole"), 50)
    momentum = _safe_float(row.get("Score momentum"), 50)
    technical = _safe_float(row.get("Score technique"), 50)
    risk = _safe_float(row.get("Score risque"), 50)
    change = _safe_float(row.get("Variation"), 0)
    rsi = _safe_float(row.get("RSI14"), np.nan)

    if score >= 72 and momentum >= 65 and risk >= 45:
        return "Leadership à confirmer"
    if momentum >= 70 and risk < 42:
        return "Fort mais volatil"
    if score >= 62 and change < 0:
        return "Repli de qualité à surveiller"
    if technical <= 35 or (not np.isnan(rsi) and rsi < 32):
        return "Pression technique"
    if score <= 40:
        return "Fragilité relative"
    return "Neutre / à comparer"


def _row_thesis(row: pd.Series) -> str:
    parts: list[str] = []
    score = _safe_float(row.get("Score Anatole"), 50)
    momentum = _safe_float(row.get("Score momentum"), 50)
    value = _safe_float(row.get("Score valorisation"), 50)
    income = _safe_float(row.get("Score revenu"), 50)
    if score >= 70:
        parts.append("profil statistique supérieur dans l’univers actif")
    elif score <= 40:
        parts.append("profil relatif faible dans l’univers actif")
    else:
        parts.append("profil intermédiaire")
    if momentum >= 65:
        parts.append("momentum favorable")
    elif momentum <= 35:
        parts.append("momentum défavorable")
    if value >= 65:
        parts.append("valorisation relative plus attractive")
    if income >= 70:
        parts.append("rendement de revenu supérieur")
    return "; ".join(parts).capitalize() + "."


def _row_checks(row: pd.Series) -> str:
    checks: list[str] = []
    rsi = _safe_float(row.get("RSI14"), np.nan)
    vol = _safe_float(row.get("VolumeRelatif"), np.nan)
    pe = _safe_float(row.get("TrailingPE"), np.nan)
    if not np.isnan(rsi) and rsi > 70:
        checks.append("RSI élevé")
    if not np.isnan(rsi) and rsi < 30:
        checks.append("RSI très bas")
    if not np.isnan(vol) and vol >= 1.7:
        checks.append("volume inhabituel")
    if np.isnan(pe):
        checks.append("valorisation à compléter")
    if not checks:
        checks.append("confirmer avec nouvelles et fondamentaux")
    return ", ".join(checks)


def _row_risk(row: pd.Series) -> str:
    risk = _safe_float(row.get("Score risque"), 50)
    change = _safe_float(row.get("Variation"), 0)
    momentum = _safe_float(row.get("Score momentum"), 50)
    if risk < 35:
        return "Volatilité / bêta élevé"
    if change <= -3:
        return "Pression de séance"
    if momentum < 35:
        return "Tendance faible"
    return "À valider par les données fondamentales"


def market_regime(frame: pd.DataFrame | None) -> RegimeSnapshot:
    work = prepare_market_frame(frame)
    if work.empty or work["Variation"].notna().sum() == 0:
        return RegimeSnapshot("Données partielles", "À vérifier", np.nan, np.nan, np.nan, 0, 0, "N/D", "N/D", np.nan, "Couverture limitée")

    valid = work.dropna(subset=["Variation"]).copy()
    advancers = int((valid["Variation"] > 0).sum())
    decliners = int((valid["Variation"] < 0).sum())
    breadth = advancers / max(1, advancers + decliners)
    average_change = float(valid["Variation"].mean())
    weights = pd.to_numeric(valid.get("PoidsIndice"), errors="coerce").fillna(0)
    if weights.sum() > 0:
        weighted_change = float(np.average(valid["Variation"], weights=weights))
        concentration = float((weights.sort_values(ascending=False).head(10).sum() / weights.sum()) * 100)
    else:
        weighted_change = average_change
        concentration = np.nan

    sector = sector_rotation(valid)
    top_sector = str(sector.iloc[0]["Secteur"]) if not sector.empty else "N/D"
    bottom_sector = str(sector.iloc[-1]["Secteur"]) if not sector.empty else "N/D"

    if breadth >= 0.62 and weighted_change > 0.35:
        label = "Appétit pour le risque"
        tone = "Participation large et positive"
    elif breadth <= 0.38 and weighted_change < -0.35:
        label = "Aversion au risque"
        tone = "Pression large sur le marché"
    elif abs(weighted_change) < 0.25 and abs(breadth - 0.5) < 0.12:
        label = "Marché d’attente"
        tone = "Équilibre fragile entre acheteurs et vendeurs"
    elif weighted_change > 0 and breadth < 0.48:
        label = "Hausse concentrée"
        tone = "Quelques poids lourds portent l’indice"
    elif weighted_change < 0 and breadth > 0.52:
        label = "Baisse concentrée"
        tone = "Quelques titres pèsent fortement sur l’indice"
    else:
        label = "Rotation sectorielle"
        tone = "Mouvements dispersés selon les secteurs"

    if concentration >= 55:
        risk_level = "Concentration élevée"
    elif concentration >= 42:
        risk_level = "Concentration modérée"
    else:
        risk_level = "Diffusion acceptable"

    return RegimeSnapshot(label, tone, breadth, average_change, weighted_change, advancers, decliners, top_sector, bottom_sector, concentration, risk_level)


def sector_rotation(frame: pd.DataFrame | None) -> pd.DataFrame:
    work = prepare_market_frame(frame)
    if work.empty:
        return pd.DataFrame(columns=["Secteur", "Variation moyenne", "Largeur", "Titres", "Poids", "Score rotation", "Moteur", "Frein"])
    work = work.dropna(subset=["Variation"]).copy()
    if work.empty:
        return pd.DataFrame(columns=["Secteur", "Variation moyenne", "Largeur", "Titres", "Poids", "Score rotation", "Moteur", "Frein"])
    rows = []
    for sector, group in work.groupby("Secteur", dropna=False):
        weight = pd.to_numeric(group.get("PoidsIndice"), errors="coerce").fillna(0)
        top = group.sort_values("Variation", ascending=False).head(1)
        bottom = group.sort_values("Variation", ascending=True).head(1)
        rows.append(
            {
                "Secteur": str(sector or "Autre"),
                "Variation moyenne": float(group["Variation"].mean()),
                "Largeur": float((group["Variation"] > 0).mean() * 100),
                "Titres": int(len(group)),
                "Poids": float(weight.sum()) if weight.sum() > 0 else np.nan,
                "Moteur": "N/D" if top.empty else f"{top.iloc[0].get('Ticker')} ({_pct(top.iloc[0].get('Variation'))})",
                "Frein": "N/D" if bottom.empty else f"{bottom.iloc[0].get('Ticker')} ({_pct(bottom.iloc[0].get('Variation'))})",
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["Score rotation"] = (
        _rank_score(result["Variation moyenne"], higher_is_better=True) * 0.65
        + _rank_score(result["Largeur"], higher_is_better=True) * 0.35
    ).round(1)
    return result.sort_values(["Score rotation", "Variation moyenne"], ascending=False).reset_index(drop=True)


def detect_dislocations(frame: pd.DataFrame | None, *, limit: int = 30) -> pd.DataFrame:
    scored = score_titles(frame)
    if scored.empty:
        return scored
    work = scored.copy()
    conditions = []
    if "RSI14" in work:
        conditions.append(pd.to_numeric(work["RSI14"], errors="coerce").between(25, 38))
        conditions.append(pd.to_numeric(work["RSI14"], errors="coerce") >= 70)
    if "Variation" in work:
        conditions.append(pd.to_numeric(work["Variation"], errors="coerce").abs() >= 2.5)
    if "VolumeRelatif" in work:
        conditions.append(pd.to_numeric(work["VolumeRelatif"], errors="coerce") >= 1.5)
    if not conditions:
        return work.head(limit)
    mask = conditions[0]
    for condition in conditions[1:]:
        mask = mask | condition
    result = work.loc[mask].copy()
    if result.empty:
        result = work.head(limit).copy()
    return result.sort_values("Score Anatole", ascending=False).head(limit).reset_index(drop=True)


def institutional_watchlist(frame: pd.DataFrame | None, *, limit: int = 15) -> pd.DataFrame:
    scored = score_titles(frame)
    if scored.empty:
        return scored
    candidates = scored.copy()
    # Priorité aux profils forts mais pas extrêmes, pour éviter une simple liste de titres déjà surachetés.
    rsi = pd.to_numeric(candidates.get("RSI14"), errors="coerce")
    candidates["Priorité analyse"] = candidates["Score Anatole"]
    candidates.loc[rsi > 75, "Priorité analyse"] -= 8
    candidates.loc[rsi < 25, "Priorité analyse"] -= 5
    candidates = candidates.sort_values("Priorité analyse", ascending=False)
    return candidates.head(limit).drop(columns=["Priorité analyse"], errors="ignore").reset_index(drop=True)


def _find_ticker(frame: pd.DataFrame, ticker: str) -> pd.Series | None:
    if frame.empty or not ticker:
        return None
    clean = str(ticker).upper().replace(".TO", "").strip()
    work = frame.copy()
    for col in ["Ticker", "YahooTicker"]:
        if col in work:
            mask = work[col].fillna("").astype(str).str.upper().str.replace(".TO", "", regex=False).eq(clean)
            if mask.any():
                return work.loc[mask].iloc[0]
    return None


def explain_ticker(frame: pd.DataFrame | None, ticker: str) -> str:
    scored = score_titles(frame)
    row = _find_ticker(scored, ticker)
    if row is None:
        return "Le titre demandé n’a pas été trouvé dans l’univers actif."
    return (
        f"## {_clean_text(row.get('Ticker'))} — {_clean_text(row.get('Nom'))}\n"
        f"**Secteur :** {_clean_text(row.get('Secteur'))}  \n"
        f"**Score Anatole :** {_num(row.get('Score Anatole'), 1)}/100 · **Catégorie :** {_clean_text(row.get('Catégorie'))}\n\n"
        f"### Lecture\n{_clean_text(row.get('Lecture Anatole'))}\n\n"
        f"### Tableau de bord\n"
        f"- Prix : {_num(row.get('Prix'), 2)} $\n"
        f"- Variation : {_pct(row.get('Variation'))}\n"
        f"- RSI : {_num(row.get('RSI14'), 1)}\n"
        f"- Volume relatif : {_num(row.get('VolumeRelatif'), 2)}x\n"
        f"- Rendement de dividende : {_pct(row.get('DividendYield'), 2, signed=False)}\n"
        f"- P/E observé : {_num(row.get('TrailingPE'), 1)}\n\n"
        f"### Points à vérifier\n- {_clean_text(row.get('Points à vérifier'))}\n"
        f"- Risque principal : {_clean_text(row.get('Risque principal'))}\n\n"
        "Cette lecture sert à prioriser l’analyse. Elle ne constitue pas une recommandation personnalisée."
    )


def build_institutional_brief(frame: pd.DataFrame | None) -> str:
    work = prepare_market_frame(frame)
    regime = market_regime(work)
    sectors = sector_rotation(work)
    radar = institutional_watchlist(work, limit=5)
    dislocations = detect_dislocations(work, limit=5)

    lines = [
        "## Brief institutionnel Anatole",
        f"**Régime :** {regime.label} — {regime.tone}",
        f"**Largeur :** {_pct(regime.breadth * 100 if not np.isnan(regime.breadth) else np.nan, 1, signed=False)} · {regime.advancers} titres en hausse / {regime.decliners} en baisse",
        f"**Mouvement pondéré :** {_pct(regime.weighted_change)} · **Risque :** {regime.risk_level}",
        "",
        "### Rotation sectorielle",
    ]
    if not sectors.empty:
        for _, row in sectors.head(4).iterrows():
            lines.append(
                f"- {row['Secteur']} : {_pct(row['Variation moyenne'])}, largeur {_pct(row['Largeur'], 0, signed=False)} — moteur {row['Moteur']}; frein {row['Frein']}"
            )
    else:
        lines.append("- Rotation non disponible.")

    lines.append("\n### Titres à étudier en priorité")
    if not radar.empty:
        for _, row in radar.iterrows():
            lines.append(
                f"- {row['Ticker']} · score {_num(row['Score Anatole'], 1)}/100 · {row['Catégorie']} · {row['Risque principal']}"
            )
    else:
        lines.append("- Aucun titre prioritaire avec les données disponibles.")

    lines.append("\n### Anomalies et dislocations")
    if not dislocations.empty:
        for _, row in dislocations.head(5).iterrows():
            lines.append(
                f"- {row['Ticker']} : variation {_pct(row.get('Variation'))}, RSI {_num(row.get('RSI14'), 1)}, volume {_num(row.get('VolumeRelatif'), 2)}x — {row.get('Points à vérifier')}"
            )
    else:
        lines.append("- Aucune anomalie majeure détectée dans l’univers actif.")

    lines.append("\n### Limites")
    lines.append("- Les scores sont des indicateurs de priorisation, pas des recommandations.")
    lines.append("- Les données peuvent être différées, incomplètes ou révisées; confirmer avec les sources officielles avant toute décision.")
    return "\n".join(lines)


def search_tickers(frame: pd.DataFrame | None, query: str, *, limit: int = 12) -> pd.DataFrame:
    work = score_titles(frame)
    if work.empty or not str(query or "").strip():
        return work.head(0)
    q = str(query).strip().lower()
    mask = (
        work["Ticker"].astype(str).str.lower().str.contains(q, regex=False)
        | work["Nom"].astype(str).str.lower().str.contains(q, regex=False)
        | work["Secteur"].astype(str).str.lower().str.contains(q, regex=False)
        | work["Catégorie"].astype(str).str.lower().str.contains(q, regex=False)
    )
    return work.loc[mask].head(limit).reset_index(drop=True)
