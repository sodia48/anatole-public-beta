from __future__ import annotations

from dataclasses import dataclass
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
        work["YahooTicker"] = work["Ticker"].astype(str).map(lambda x: x if str(x).endswith(".TO") else f"{x}.TO")
    if "Nom" not in work.columns:
        work["Nom"] = work.get("Ticker", pd.Series("N/D", index=work.index))
    if "Secteur" not in work.columns:
        work["Secteur"] = "Autre"
    for col in [
        "Prix", "Variation", "PoidsIndice", "Volume", "VolumeRelatif", "RSI14", "SMA20", "SMA50", "SMA200",
        "Rendement1M", "Rendement3M", "Rendement6M", "Rendement1Y", "Score Anatole",
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


def _sector_rotation(work: pd.DataFrame) -> pd.DataFrame:
    if work.empty or "Variation" not in work.columns:
        return pd.DataFrame(columns=["Secteur", "Variation moyenne", "Largeur", "Titres", "Moteur", "Frein"])
    valid = work.dropna(subset=["Variation"]).copy()
    rows: list[dict[str, Any]] = []
    for sector, group in valid.groupby("Secteur", dropna=False):
        top = group.sort_values("Variation", ascending=False).head(1)
        bottom = group.sort_values("Variation", ascending=True).head(1)
        rows.append({
            "Secteur": str(sector or "Autre"),
            "Variation moyenne": float(group["Variation"].mean()),
            "Largeur": float((group["Variation"] > 0).mean() * 100),
            "Titres": int(len(group)),
            "Moteur": "N/D" if top.empty else f"{top.iloc[0].get('Ticker')} ({_pct(top.iloc[0].get('Variation'))})",
            "Frein": "N/D" if bottom.empty else f"{bottom.iloc[0].get('Ticker')} ({_pct(bottom.iloc[0].get('Variation'))})",
        })
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values(["Variation moyenne", "Largeur"], ascending=False).reset_index(drop=True)


def _choose_market_label(breadth: float, weighted_change: float, avg_change: float) -> tuple[str, str, str]:
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
    if abs(avg_change) < 0.25:
        return "Marché d’attente", "neutre", "Le marché manque de direction claire et la sélection titre par titre devient importante."
    return "Rotation active", "sélectif", "Les mouvements sont surtout expliqués par des rotations sectorielles."


def _watchlist_frame(work: pd.DataFrame, watchlist: list[str] | tuple[str, ...] | None) -> pd.DataFrame:
    if work.empty or not watchlist:
        return pd.DataFrame()
    wanted = {_clean_symbol(x) for x in watchlist if str(x or "").strip()}
    if not wanted:
        return pd.DataFrame()
    mask = work["Ticker"].map(_clean_symbol).isin(wanted) | work.get("YahooTicker", work["Ticker"]).map(_clean_symbol).isin(wanted)
    result = work.loc[mask].copy()
    if "Variation" in result.columns:
        result = result.sort_values("Variation", ascending=False)
    return result.reset_index(drop=True)


def _action_score(work: pd.DataFrame) -> pd.DataFrame:
    if work.empty:
        return pd.DataFrame()
    result = work.copy()
    variation_abs = pd.to_numeric(result.get("Variation"), errors="coerce").abs().fillna(0)
    volume_rel = pd.to_numeric(result.get("VolumeRelatif"), errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(1.0)
    rsi = pd.to_numeric(result.get("RSI14"), errors="coerce")
    score_anatole = pd.to_numeric(result.get("Score Anatole"), errors="coerce").fillna(50)
    rsi_extreme = (rsi - 50).abs().fillna(0)
    result["Priorité"] = (variation_abs * 12 + (volume_rel - 1).clip(lower=0) * 20 + rsi_extreme * 0.35 + score_anatole * 0.20).clip(0, 100).round(1)
    def reason(row: pd.Series) -> str:
        reasons: list[str] = []
        if _safe_float(row.get("Variation")) >= 2:
            reasons.append("forte hausse")
        elif _safe_float(row.get("Variation")) <= -2:
            reasons.append("forte baisse")
        if _safe_float(row.get("VolumeRelatif")) >= 1.5:
            reasons.append("volume inhabituel")
        if _safe_float(row.get("RSI14")) >= 70:
            reasons.append("RSI élevé")
        elif _safe_float(row.get("RSI14")) <= 30:
            reasons.append("RSI faible")
        if _safe_float(row.get("Score Anatole")) >= 70:
            reasons.append("profil Anatole solide")
        return ", ".join(reasons) if reasons else "à comparer avec le secteur"
    result["Pourquoi suivre"] = result.apply(reason, axis=1)
    columns = ["Ticker", "Nom", "Secteur", "Variation", "RSI14", "VolumeRelatif", "Score Anatole", "Priorité", "Pourquoi suivre", "YahooTicker"]
    return result[[c for c in columns if c in result.columns]].sort_values("Priorité", ascending=False).head(20).reset_index(drop=True)


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
        )

    variation = pd.to_numeric(work.get("Variation"), errors="coerce")
    valid = work.loc[variation.notna()].copy()
    valid["Variation"] = variation.loc[valid.index]
    advancers = int((valid["Variation"] > 0).sum())
    decliners = int((valid["Variation"] < 0).sum())
    unchanged = int((valid["Variation"] == 0).sum())
    breadth = advancers / max(advancers + decliners, 1)
    avg_change = float(valid["Variation"].mean()) if not valid.empty else np.nan
    weights = pd.to_numeric(valid.get("PoidsIndice"), errors="coerce").fillna(0) if not valid.empty else pd.Series(dtype=float)
    weighted_change = float(np.average(valid["Variation"], weights=weights)) if not valid.empty and weights.sum() > 0 else avg_change
    label, tone, interpretation = _choose_market_label(breadth, weighted_change, avg_change)

    sectors = _sector_rotation(work)
    leaders = valid.sort_values("Variation", ascending=False).head(10).reset_index(drop=True)
    laggards = valid.sort_values("Variation", ascending=True).head(10).reset_index(drop=True)
    unusual = _action_score(work)
    wframe = _watchlist_frame(work, watchlist)
    actions = _action_score(work)

    best_sector = sectors.iloc[0]["Secteur"] if not sectors.empty else "N/D"
    worst_sector = sectors.iloc[-1]["Secteur"] if not sectors.empty else "N/D"
    top_leader = leaders.iloc[0]["Ticker"] if not leaders.empty else "N/D"
    top_laggard = laggards.iloc[0]["Ticker"] if not laggards.empty else "N/D"

    executive_summary = [
        f"Régime détecté : {label}. {interpretation}",
        f"Participation : {advancers} titres en hausse contre {decliners} en baisse; largeur estimée à {_pct(breadth * 100, 0, signed=False)}.",
        f"Rotation : meilleur secteur {best_sector}, secteur le plus faible {worst_sector}.",
        f"Titres extrêmes à vérifier : {top_leader} du côté positif, {top_laggard} du côté négatif.",
    ]
    if not wframe.empty:
        best_watch = wframe.sort_values("Variation", ascending=False).iloc[0]
        worst_watch = wframe.sort_values("Variation", ascending=True).iloc[0]
        executive_summary.append(
            f"Watchlist : {best_watch.get('Ticker')} se distingue positivement ({_pct(best_watch.get('Variation'))}); {worst_watch.get('Ticker')} pèse le plus ({_pct(worst_watch.get('Variation'))})."
        )

    watch_items = [
        f"Confirmer si {best_sector} continue de mener la rotation ou si le mouvement s’essouffle.",
        "Vérifier si les volumes confirment les plus fortes variations.",
        "Comparer les gagnants du jour avec les leaders du Terminal Pro.",
        "Surveiller les titres de la watchlist dont le mouvement dépasse le secteur.",
    ]
    next_questions = [
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
        "best_sector": best_sector,
        "worst_sector": worst_sector,
        "coverage": int(len(work)),
    }
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
    )


def build_today_markdown(market: pd.DataFrame | None, watchlist: list[str] | tuple[str, ...] | None = None) -> str:
    brief = build_today_brief(market, watchlist)
    lines = [
        "## Aujourd’hui sur le marché",
        f"**Régime :** {brief.market_label} · **Ton :** {brief.tone}",
        "",
        "### Résumé exécutif",
    ]
    lines.extend(f"- {item}" for item in brief.executive_summary)
    if not brief.sectors.empty:
        lines.append("\n### Rotation sectorielle")
        for _, row in brief.sectors.head(5).iterrows():
            lines.append(f"- **{row.get('Secteur')}** : {_pct(row.get('Variation moyenne'))}, largeur {_pct(row.get('Largeur'), 0, signed=False)} · moteur {row.get('Moteur')} · frein {row.get('Frein')}")
    if not brief.actions.empty:
        lines.append("\n### Titres à suivre en priorité")
        for _, row in brief.actions.head(7).iterrows():
            lines.append(f"- **{row.get('Ticker')}** — {_pct(row.get('Variation'))}, RSI {_num(row.get('RSI14'))}, priorité {_num(row.get('Priorité'))}/100 : {row.get('Pourquoi suivre')}")
    lines.append("\n### À vérifier ensuite")
    lines.extend(f"- {item}" for item in brief.watch_items)
    lines.append("\nCette synthèse sert à prioriser l’analyse. Elle ne constitue pas une recommandation personnalisée.")
    return "\n".join(lines)
