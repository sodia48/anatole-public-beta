from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from core.config import TORONTO_TZ


def missing_share(frame: pd.DataFrame, columns: list[str]) -> float:
    if frame.empty or not columns:
        return 1.0
    available = [column for column in columns if column in frame]
    if not available:
        return 1.0
    return float(frame[available].isna().mean().mean())


def quality_label(frame: pd.DataFrame, required_columns: list[str]) -> tuple[str, str]:
    missing = missing_share(frame, required_columns)
    if missing <= 0.05:
        return "Excellent", "🟢"
    if missing <= 0.18:
        return "Bon", "🟡"
    if missing <= 0.35:
        return "Partiel", "🟠"
    return "Fragile", "🔴"


def source_summary(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "Aucune donnée disponible"
    sources = (
        frame.get("SourceCours", pd.Series(dtype=str))
        .dropna()
        .astype(str)
        .value_counts()
        .head(3)
    )
    if sources.empty:
        return "Source non précisée"
    return " · ".join(f"{name} ({count})" for name, count in sources.items())


def last_update_text(frame: pd.DataFrame) -> str:
    if frame.empty or "Horodatage" not in frame:
        return datetime.now(TORONTO_TZ).strftime("%H:%M ET")
    stamps = pd.to_datetime(frame["Horodatage"], errors="coerce", utc=True).dropna()
    if stamps.empty:
        return datetime.now(TORONTO_TZ).strftime("%H:%M ET")
    latest = stamps.max().tz_convert(TORONTO_TZ)
    return latest.strftime("%H:%M ET")


def render_data_quality_strip(
    frame: pd.DataFrame,
    diagnostics: dict[str, Any] | None = None,
    compact: bool = False,
) -> None:
    diagnostics = diagnostics or {}
    label, icon = quality_label(frame, ["Prix", "Variation", "Volume"])
    source = source_summary(frame)
    update = last_update_text(frame)
    universe = diagnostics.get("universe_label") or diagnostics.get("Univers") or "Univers actif"
    displayed = diagnostics.get("displayed")
    actual = diagnostics.get("actual")
    size = f"{displayed} affichés"
    if actual and displayed and actual != displayed:
        size = f"{displayed}/{actual} affichés"

    message = (
        f"{icon} Qualité des données : **{label}** · "
        f"{universe} · {size} · Mise à jour : {update} · Source : {source}"
    )

    if compact:
        st.caption(message)
    else:
        st.info(message)


def render_source_status() -> None:
    rows = [
        {"Source": "Marché", "Statut": "Live / dernier snapshot valide", "Usage": "Prix, variations, volumes"},
        {"Source": "Composition", "Statut": "Cache longue durée", "Usage": "Univers TSX 60, Composite, TSX étendu"},
        {"Source": "Actualités", "Statut": "Chargement borné", "Usage": "Manchettes et sentiment"},
        {"Source": "Fondamentaux", "Statut": "Sur demande", "Usage": "Ratios financiers et données société"},
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
