from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


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


def _numeric_series(frame: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    if column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _clean_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text.replace(".TO", "")


def _clean_market_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    if "Ticker" not in work.columns and "YahooTicker" in work.columns:
        work["Ticker"] = work["YahooTicker"].astype(str).str.replace(".TO", "", regex=False)
    if "YahooTicker" not in work.columns and "Ticker" in work.columns:
        work["YahooTicker"] = work["Ticker"].astype(str).map(lambda x: x if str(x).upper().endswith(".TO") else f"{x}.TO")
    if "Nom" not in work.columns:
        work["Nom"] = work.get("Ticker", pd.Series("N/D", index=work.index))
    if "Secteur" not in work.columns:
        work["Secteur"] = "Autre"
    for col in [
        "Prix", "Variation", "PoidsIndice", "Volume", "VolumeRelatif", "RSI14", "SMA20", "SMA50", "SMA200",
        "Rendement1D", "Rendement1W", "Rendement1M", "Rendement3M", "Rendement6M", "Rendement1Y", "Score Anatole",
        "DividendYield", "Beta", "MarketCap",
    ]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work["Ticker"] = work["Ticker"].map(_clean_symbol)
    work["Nom"] = work["Nom"].fillna(work["Ticker"]).astype(str)
    work["Secteur"] = work["Secteur"].fillna("Autre").astype(str)
    work = work[work["Ticker"].astype(str).str.len() > 0]
    return work.drop_duplicates(subset=["Ticker"], keep="first").reset_index(drop=True)


@dataclass(frozen=True)
class DailyBrief:
    title: str
    tone: str
    market_label: str
    executive_summary: list[str]
    watch_items: list[str]
    next_questions: list[str]
    metrics: dict[str, Any]
    sectors: pd.DataFrame
    leaders: pd.DataFrame
    laggards: pd.DataFrame
    unusual: pd.DataFrame
    watchlist: pd.DataFrame
    actions: pd.DataFrame
    agenda: list[str] = field(default_factory=list)
    five_minute_plan: list[str] = field(default_factory=list)
    signal_cards: list[dict[str, str]] = field(default_factory=list)
    sector_story: list[str] = field(default_factory=list)
    positive_cases: pd.DataFrame = field(default_factory=pd.DataFrame)
    risk_cases: pd.DataFrame = field(default_factory=pd.DataFrame)
    watchlist_alerts: pd.DataFrame = field(default_factory=pd.DataFrame)
    market_narrative: str = ""


def _sector_signal(avg_change: float, breadth: float) -> str:
    if np.isnan(avg_change) or np.isnan(breadth):
        return "À vérifier"
    if avg_change >= 1.0 and breadth >= 65:
        return "Leadership large"
    if avg_change >= 0.35 and breadth >= 55:
        return "Rotation positive"
    if avg_change > 0 and breadth < 45:
        return "Hausse concentrée"
    if avg_change <= -1.0 and breadth <= 35:
        return "Pression large"
    if avg_change < 0 and breadth > 50:
        return "Faiblesse concentrée"
    return "Neutre / mixte"


def _sector_rotation(work: pd.DataFrame) -> pd.DataFrame:
    columns = ["Secteur", "Variation moyenne", "Largeur", "Titres", "Signal", "Moteur", "Frein", "Contribution indicative"]
    if work.empty or "Variation" not in work.columns:
        return pd.DataFrame(columns=columns)
    valid = work.dropna(subset=["Variation"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=columns)
    weights = _numeric_series(valid, "PoidsIndice", 0.0).fillna(0)
    rows: list[dict[str, Any]] = []
    for sector, group in valid.groupby("Secteur", dropna=False):
        top = group.sort_values("Variation", ascending=False).head(1)
        bottom = group.sort_values("Variation", ascending=True).head(1)
        g_weights = weights.loc[group.index] if len(weights) else pd.Series(0, index=group.index)
        contribution = float((group["Variation"] * g_weights).sum() / max(g_weights.sum(), 1e-9)) if g_weights.sum() > 0 else float(group["Variation"].mean())
        avg = float(group["Variation"].mean())
        breadth = float((group["Variation"] > 0).mean() * 100)
        rows.append({
            "Secteur": str(sector or "Autre"),
            "Variation moyenne": avg,
            "Largeur": breadth,
            "Titres": int(len(group)),
            "Signal": _sector_signal(avg, breadth),
            "Moteur": "N/D" if top.empty else f"{top.iloc[0].get('Ticker')} ({_pct(top.iloc[0].get('Variation'))})",
            "Frein": "N/D" if bottom.empty else f"{bottom.iloc[0].get('Ticker')} ({_pct(bottom.iloc[0].get('Variation'))})",
            "Contribution indicative": contribution,
        })
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["Contribution indicative", "Variation moyenne", "Largeur"], ascending=False).reset_index(drop=True)


def _choose_market_label(breadth: float, weighted_change: float, avg_change: float, dispersion: float) -> tuple[str, str, str]:
    if np.isnan(breadth):
        return "Données partielles", "Couverture limitée", "Le marché doit être vérifié avec des données plus complètes."
    if breadth >= 0.62 and weighted_change > 0.25:
        return "Risk-on canadien", "constructif", "La hausse est soutenue par une participation assez large."
    if breadth <= 0.38 and weighted_change < -0.25:
        return "Risk-off canadien", "défensif", "La pression est large et mérite une lecture prudente."
    if weighted_change > 0 and breadth < 0.48:
        return "Hausse concentrée", "sélectif", "Quelques poids lourds portent le marché pendant que la participation reste limitée."
    if weighted_change < 0 and breadth > 0.52:
        return "Baisse concentrée", "sélectif", "Une partie du marché résiste, mais certains poids lourds pèsent sur l’indice."
    if dispersion >= 2.25:
        return "Marché de dispersion", "opportuniste", "Les écarts entre gagnants et perdants sont élevés : l’analyse titre par titre devient déterminante."
    if abs(avg_change) < 0.25:
        return "Marché d’attente", "neutre", "Le marché manque de direction claire et la sélection titre par titre devient importante."
    return "Rotation active", "sélectif", "Les mouvements sont surtout expliqués par des rotations sectorielles."


def _watchlist_frame(work: pd.DataFrame, watchlist: list[str] | tuple[str, ...] | None) -> pd.DataFrame:
    if work.empty or not watchlist:
        return pd.DataFrame()
    wanted = {_clean_symbol(x) for x in watchlist if str(x or "").strip()}
    if not wanted:
        return pd.DataFrame()
    yahoo = work["YahooTicker"] if "YahooTicker" in work.columns else work["Ticker"]
    mask = work["Ticker"].map(_clean_symbol).isin(wanted) | yahoo.map(_clean_symbol).isin(wanted)
    result = work.loc[mask].copy()
    if result.empty:
        return result
    result["Priorité watchlist"] = _priority_score(result)
    result["Lecture"] = result.apply(_row_reason, axis=1)
    return result.sort_values("Priorité watchlist", ascending=False).reset_index(drop=True)


def _priority_score(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    variation_abs = _numeric_series(frame, "Variation").abs().fillna(0)
    volume_rel = _numeric_series(frame, "VolumeRelatif", 1.0).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    rsi = _numeric_series(frame, "RSI14")
    score_anatole = _numeric_series(frame, "Score Anatole", 50.0).fillna(50)
    rsi_extreme = (rsi - 50).abs().fillna(0)
    score = variation_abs * 12 + (volume_rel - 1).clip(lower=0) * 20 + rsi_extreme * 0.35 + score_anatole * 0.20
    return score.clip(0, 100).round(1)


def _row_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    variation = _safe_float(row.get("Variation"))
    volume = _safe_float(row.get("VolumeRelatif"))
    rsi = _safe_float(row.get("RSI14"))
    score = _safe_float(row.get("Score Anatole"))
    if variation >= 2:
        reasons.append("forte hausse")
    elif variation <= -2:
        reasons.append("forte baisse")
    if volume >= 1.5:
        reasons.append("volume inhabituel")
    if rsi >= 70:
        reasons.append("RSI élevé")
    elif rsi <= 30:
        reasons.append("RSI faible")
    if score >= 72:
        reasons.append("profil Anatole solide")
    elif score <= 32:
        reasons.append("profil fragile")
    return ", ".join(reasons) if reasons else "à comparer avec le secteur"


def _action_score(work: pd.DataFrame) -> pd.DataFrame:
    if work.empty:
        return pd.DataFrame()
    result = work.copy()
    result["Priorité"] = _priority_score(result)
    result["Pourquoi suivre"] = result.apply(_row_reason, axis=1)

    def role(row: pd.Series) -> str:
        variation = _safe_float(row.get("Variation"))
        priority = _safe_float(row.get("Priorité"), 0)
        if variation >= 1.5 and priority >= 45:
            return "Moteur potentiel"
        if variation <= -1.5 and priority >= 45:
            return "Risque à surveiller"
        if _safe_float(row.get("VolumeRelatif")) >= 1.6:
            return "Volume inhabituel"
        if _safe_float(row.get("Score Anatole")) >= 75:
            return "Qualité à revoir"
        return "Signal secondaire"

    result["Rôle du jour"] = result.apply(role, axis=1)
    columns = ["Ticker", "Nom", "Secteur", "Variation", "RSI14", "VolumeRelatif", "Score Anatole", "Priorité", "Rôle du jour", "Pourquoi suivre", "YahooTicker"]
    return result[[c for c in columns if c in result.columns]].sort_values("Priorité", ascending=False).head(30).reset_index(drop=True)


def _positive_cases(actions: pd.DataFrame) -> pd.DataFrame:
    if actions.empty or "Variation" not in actions.columns:
        return pd.DataFrame()
    frame = actions.copy()
    score = _numeric_series(frame, "Score Anatole", 50).fillna(50)
    mask = (_numeric_series(frame, "Variation") > 0) | (score >= 70)
    return frame.loc[mask].sort_values(["Priorité", "Variation"], ascending=False).head(8).reset_index(drop=True)


def _risk_cases(actions: pd.DataFrame) -> pd.DataFrame:
    if actions.empty or "Variation" not in actions.columns:
        return pd.DataFrame()
    frame = actions.copy()
    mask = (_numeric_series(frame, "Variation") < 0) | (_numeric_series(frame, "RSI14", 50) < 35)
    return frame.loc[mask].sort_values(["Priorité", "Variation"], ascending=[False, True]).head(8).reset_index(drop=True)


def _signal_cards(label: str, tone: str, metrics: dict[str, Any], sectors: pd.DataFrame, actions: pd.DataFrame) -> list[dict[str, str]]:
    best_sector = str(metrics.get("best_sector", "N/D"))
    worst_sector = str(metrics.get("worst_sector", "N/D"))
    top_action = "N/D" if actions.empty else str(actions.iloc[0].get("Ticker", "N/D"))
    top_reason = "Aucun signal prioritaire" if actions.empty else str(actions.iloc[0].get("Pourquoi suivre", "signal à vérifier"))
    breadth = metrics.get("breadth")
    weighted = metrics.get("weighted_change")
    return [
        {"titre": "Régime", "valeur": label, "detail": f"Ton : {tone}"},
        {"titre": "Participation", "valeur": _pct(breadth, 0, signed=False), "detail": "part des titres en hausse"},
        {"titre": "Mouvement", "valeur": _pct(weighted), "detail": "variation pondérée indicative"},
        {"titre": "Secteur moteur", "valeur": best_sector, "detail": f"à comparer avec {worst_sector}"},
        {"titre": "Signal titre", "valeur": top_action, "detail": top_reason},
    ]


def _sector_story(sectors: pd.DataFrame) -> list[str]:
    if sectors.empty:
        return ["La rotation sectorielle n’est pas disponible avec les données actuelles."]
    top = sectors.head(3)
    bottom = sectors.tail(3).sort_values("Variation moyenne")
    story = [
        "Secteurs en leadership : " + ", ".join(f"{r.get('Secteur')} ({_pct(r.get('Variation moyenne'))})" for _, r in top.iterrows()),
        "Secteurs sous pression : " + ", ".join(f"{r.get('Secteur')} ({_pct(r.get('Variation moyenne'))})" for _, r in bottom.iterrows()),
    ]
    concentrated = sectors[(sectors["Variation moyenne"] > 0) & (sectors["Largeur"] < 45)]
    if not concentrated.empty:
        story.append("Attention : certaines hausses sectorielles semblent concentrées sur peu de titres.")
    pressured = sectors[(sectors["Variation moyenne"] < 0) & (sectors["Largeur"] < 35)]
    if not pressured.empty:
        story.append("Signal de prudence : au moins un secteur montre une pression large.")
    return story


def build_today_brief(market: pd.DataFrame | None, watchlist: list[str] | tuple[str, ...] | None = None) -> DailyBrief:
    work = _clean_market_frame(market)
    if work.empty:
        return DailyBrief(
            title="Aujourd’hui sur le marché",
            tone="Données limitées",
            market_label="Données partielles",
            executive_summary=["Les données de marché ne sont pas encore disponibles dans cette session."],
            watch_items=["Relancer le chargement de l’univers actif.", "Vérifier la disponibilité des données de marché."],
            next_questions=["Pourquoi les données ne sont pas disponibles ?", "Que puis-je analyser avec les données actuelles ?"],
            metrics={},
            sectors=pd.DataFrame(),
            leaders=pd.DataFrame(),
            laggards=pd.DataFrame(),
            unusual=pd.DataFrame(),
            watchlist=pd.DataFrame(),
            actions=pd.DataFrame(),
            agenda=["Attendre le chargement complet des données avant de conclure."],
            five_minute_plan=["Actualiser les données", "Ouvrir le cockpit", "Vérifier la watchlist"],
            signal_cards=[],
            market_narrative="Les données disponibles sont insuffisantes pour construire un brief fiable.",
        )

    variation = _numeric_series(work, "Variation")
    valid = work.loc[variation.notna()].copy()
    valid["Variation"] = variation.loc[valid.index]
    advancers = int((valid["Variation"] > 0).sum())
    decliners = int((valid["Variation"] < 0).sum())
    unchanged = int((valid["Variation"] == 0).sum())
    breadth = advancers / max(advancers + decliners, 1)
    avg_change = float(valid["Variation"].mean()) if not valid.empty else np.nan
    dispersion = float(valid["Variation"].std()) if len(valid) > 2 else np.nan
    weights = _numeric_series(valid, "PoidsIndice", 0.0).fillna(0) if not valid.empty else pd.Series(dtype=float)
    weighted_change = float(np.average(valid["Variation"], weights=weights)) if not valid.empty and weights.sum() > 0 else avg_change
    label, tone, interpretation = _choose_market_label(breadth, weighted_change, avg_change, dispersion)

    sectors = _sector_rotation(work)
    leaders = valid.sort_values("Variation", ascending=False).head(10).reset_index(drop=True)
    laggards = valid.sort_values("Variation", ascending=True).head(10).reset_index(drop=True)
    actions = _action_score(work)
    unusual = actions[_numeric_series(actions, "VolumeRelatif", 0).fillna(0) >= 1.4].head(10).reset_index(drop=True) if not actions.empty else pd.DataFrame()
    wframe = _watchlist_frame(work, watchlist)
    positive = _positive_cases(actions)
    risk = _risk_cases(actions)
    walerts = wframe.head(8).copy() if not wframe.empty else pd.DataFrame()

    best_sector = sectors.iloc[0]["Secteur"] if not sectors.empty else "N/D"
    worst_sector = sectors.iloc[-1]["Secteur"] if not sectors.empty else "N/D"
    top_leader = leaders.iloc[0]["Ticker"] if not leaders.empty else "N/D"
    top_laggard = laggards.iloc[0]["Ticker"] if not laggards.empty else "N/D"
    top_action = actions.iloc[0]["Ticker"] if not actions.empty else "N/D"

    executive_summary = [
        f"Régime détecté : {label}. {interpretation}",
        f"Participation : {advancers} titres en hausse contre {decliners} en baisse; largeur estimée à {_pct(breadth * 100, 0, signed=False)}.",
        f"Rotation : meilleur secteur {best_sector}, secteur le plus faible {worst_sector}.",
        f"Titres extrêmes à vérifier : {top_leader} du côté positif, {top_laggard} du côté négatif.",
    ]
    if not unusual.empty:
        executive_summary.append(f"Volume inhabituel : {unusual.iloc[0].get('Ticker')} ressort comme premier dossier à valider.")
    if not wframe.empty:
        best_watch = wframe.sort_values("Variation", ascending=False).iloc[0]
        worst_watch = wframe.sort_values("Variation", ascending=True).iloc[0]
        executive_summary.append(
            f"Watchlist : {best_watch.get('Ticker')} se distingue positivement ({_pct(best_watch.get('Variation'))}); {worst_watch.get('Ticker')} pèse le plus ({_pct(worst_watch.get('Variation'))})."
        )

    agenda = [
        f"Vérifier si le secteur {best_sector} confirme son leadership avec plusieurs titres, pas seulement un poids lourd.",
        f"Comprendre pourquoi {top_action} est prioritaire dans le radar du jour.",
        f"Comparer {top_leader} et {top_laggard} dans Focus pour distinguer mouvement durable et simple bruit de séance.",
        "Regarder les volumes relatifs avant de conclure sur un changement de tendance.",
    ]
    if not walerts.empty:
        agenda.insert(1, "Passer en revue la watchlist : au moins un titre personnel ressort dans le brief.")

    five_minute_plan = [
        "Lire le régime de marché et la largeur pour comprendre le contexte.",
        f"Ouvrir le secteur {best_sector} et vérifier les moteurs principaux.",
        f"Analyser {top_action} dans Focus ou Terminal Pro.",
        "Contrôler les dossiers de la watchlist qui divergent du marché.",
        "Envoyer une question rapide à l’assistant pour obtenir la lecture comité d’investissement.",
    ]

    watch_items = [
        f"Confirmer si {best_sector} continue de mener la rotation ou si le mouvement s’essouffle.",
        "Vérifier si les volumes confirment les plus fortes variations.",
        "Comparer les gagnants du jour avec les leaders du Terminal Pro.",
        "Surveiller les titres de la watchlist dont le mouvement dépasse le secteur.",
    ]
    next_questions = [
        "Fais-moi le brief du jour Anatole.",
        "Pourquoi le marché bouge aujourd’hui ?",
        "Quels titres expliquent le mouvement du TSX ?",
        "Quelles dislocations méritent une vérification ?",
        "Quels secteurs montrent une vraie rotation ?",
        "Fais-moi un brief comité d’investissement sur la séance.",
    ]
    metrics = {
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
        "breadth": breadth * 100,
        "average_change": avg_change,
        "weighted_change": weighted_change,
        "dispersion": dispersion,
        "best_sector": best_sector,
        "worst_sector": worst_sector,
        "coverage": int(len(work)),
        "priority_count": int(len(actions)),
        "watchlist_hits": int(len(wframe)),
        "unusual_count": int(len(unusual)),
    }
    narrative = (
        f"Anatole lit la séance comme un marché {tone}. Le cœur de l’analyse n’est pas seulement la direction de l’indice, "
        f"mais la qualité de la participation, la rotation sectorielle et les titres dont le mouvement mérite une validation. "
        f"Aujourd’hui, le dossier central est {best_sector}, tandis que {worst_sector} sert de zone de risque ou de contrepoids."
    )
    return DailyBrief(
        title="Aujourd’hui sur le marché",
        tone=tone,
        market_label=label,
        executive_summary=executive_summary,
        watch_items=watch_items,
        next_questions=next_questions,
        metrics=metrics,
        sectors=sectors,
        leaders=leaders,
        laggards=laggards,
        unusual=unusual,
        watchlist=wframe,
        actions=actions,
        agenda=agenda,
        five_minute_plan=five_minute_plan,
        signal_cards=_signal_cards(label, tone, metrics, sectors, actions),
        sector_story=_sector_story(sectors),
        positive_cases=positive,
        risk_cases=risk,
        watchlist_alerts=walerts,
        market_narrative=narrative,
    )


def build_today_markdown(market: pd.DataFrame | None, watchlist: list[str] | tuple[str, ...] | None = None) -> str:
    brief = build_today_brief(market, watchlist)
    lines = [
        "## Aujourd’hui sur le marché",
        f"**Régime :** {brief.market_label} · **Ton :** {brief.tone}",
        "",
        "### Lecture en 5 minutes",
    ]
    lines.extend(f"- {item}" for item in brief.five_minute_plan)
    lines.extend(["", "### Résumé exécutif"])
    lines.extend(f"- {item}" for item in brief.executive_summary)
    if not brief.sectors.empty:
        lines.append("\n### Rotation sectorielle")
        for _, row in brief.sectors.head(5).iterrows():
            lines.append(f"- **{row.get('Secteur')}** : {_pct(row.get('Variation moyenne'))}, largeur {_pct(row.get('Largeur'), 0, signed=False)} · {row.get('Signal')} · moteur {row.get('Moteur')} · frein {row.get('Frein')}")
    if not brief.actions.empty:
        lines.append("\n### Titres à suivre en priorité")
        for _, row in brief.actions.head(7).iterrows():
            lines.append(f"- **{row.get('Ticker')}** — {_pct(row.get('Variation'))}, RSI {_num(row.get('RSI14'))}, priorité {_num(row.get('Priorité'))}/100 : {row.get('Pourquoi suivre')}")
    lines.append("\n### Agenda d’analyse")
    lines.extend(f"- {item}" for item in brief.agenda)
    lines.append("\nCette synthèse sert à prioriser l’analyse. Elle ne constitue pas une recommandation personnalisée.")
    return "\n".join(lines)
