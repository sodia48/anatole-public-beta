from __future__ import annotations

import pandas as pd
import streamlit as st

import logging

from core.analytics import build_feature_table
from core.data import fetch_batch_history, fetch_market_snapshot, load_constituents
from core.universe import DEFAULT_UNIVERSE_KEY, current_universe_key, get_universe


def _active_constituents(constituents: pd.DataFrame, limit: int) -> pd.DataFrame:
    if constituents.empty:
        return constituents
    work = constituents.copy()
    work["PoidsIndice"] = pd.to_numeric(work.get("PoidsIndice"), errors="coerce").fillna(0)
    return work.sort_values("PoidsIndice", ascending=False).head(limit).reset_index(drop=True)



def _market_data_status(market: pd.DataFrame) -> str:
    if market.empty or "StatutDonnee" not in market:
        return "Non précisé"
    values = (
        market["StatutDonnee"]
        .dropna()
        .astype(str)
        .value_counts()
        .head(3)
    )
    if values.empty:
        return "Non précisé"
    return " · ".join(f"{name} ({count})" for name, count in values.items())

def _empty_market_frame(active: pd.DataFrame) -> pd.DataFrame:
    market = active.copy()
    for column in [
        "Prix",
        "CloturePrecedente",
        "Variation",
        "PlusHaut",
        "PlusBas",
        "Volume",
        "SourceCours",
        "Horodatage",
    ]:
        if column not in market.columns:
            market[column] = pd.NA
    return market



@st.cache_data(ttl=60, max_entries=8, show_spinner=False)
def _load_light_market_bundle_cached(
    universe_key: str,
) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Chargement léger : composition complète + snapshot limité."""
    universe = get_universe(universe_key)
    constituents, diagnostics = load_constituents(universe_key)
    active = _active_constituents(constituents, universe.snapshot_limit)
    tickers = tuple(active["YahooTicker"].tolist())
    snapshot = fetch_market_snapshot(tickers)
    market = active.merge(snapshot, on="YahooTicker", how="left")
    diagnostics = dict(diagnostics)
    diagnostics["displayed"] = len(active)
    diagnostics["universe_label"] = universe.label
    diagnostics["data_status"] = _market_data_status(market)
    return constituents, diagnostics, market


def load_light_market_bundle() -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """API compatible avec les pages existantes, sans retour silencieux au TSX 60."""
    key = current_universe_key()
    try:
        return _load_light_market_bundle_cached(key)
    except Exception as exc:
        logging.exception("Échec de l'univers %s.", key)
        universe = get_universe(key)
        constituents, diagnostics = load_constituents(key)
        active = _active_constituents(constituents, universe.snapshot_limit)
        market = _empty_market_frame(active)
        diagnostics = dict(diagnostics)
        diagnostics["status"] = "Univers partiel"
        diagnostics["displayed"] = len(active)
        diagnostics["universe_label"] = universe.label
        diagnostics["data_status"] = _market_data_status(market)
        diagnostics["universe_key"] = key
        diagnostics["error"] = (
            f"L'univers sélectionné ({universe.short_label}) est affiché en mode partiel : "
            f"{type(exc).__name__}."
        )
        return constituents, diagnostics, market


@st.cache_data(ttl=1_800, max_entries=8, show_spinner=False)
def _load_technical_bundle_cached(
    universe_key: str,
) -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    """Chargement technique plus lourd, borné par univers."""
    universe = get_universe(universe_key)
    constituents, diagnostics, market = _load_light_market_bundle_cached(universe_key)
    active = _active_constituents(constituents, universe.history_limit)
    # Réutiliser les titres déjà affichés lorsque possible.
    tickers = tuple(active["YahooTicker"].tolist())
    histories = fetch_batch_history(tickers, "1y", "1d")
    snapshot_columns = [
        column
        for column in [
            "YahooTicker",
            "Prix",
            "CloturePrecedente",
            "Variation",
            "PlusHaut",
            "PlusBas",
            "Volume",
            "SourceCours",
            "Horodatage",
        ]
        if column in market.columns
    ]
    snapshot = market[snapshot_columns].copy() if snapshot_columns else pd.DataFrame()
    features = build_feature_table(active, histories, snapshot)
    diagnostics = dict(diagnostics)
    diagnostics["technical_displayed"] = len(active)
    return constituents, diagnostics, market, features


def load_technical_bundle() -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    key = current_universe_key()
    try:
        return _load_technical_bundle_cached(key)
    except Exception as exc:
        logging.exception("Échec technique de l'univers %s.", key)
        constituents, diagnostics, market = load_light_market_bundle()
        features = market.copy()
        diagnostics = dict(diagnostics)
        diagnostics["status"] = "Technique partiel"
        diagnostics["universe_key"] = key
        diagnostics["error"] = (
            f"Les indicateurs techniques de l'univers sélectionné sont temporairement partiels : "
            f"{type(exc).__name__}."
        )
        return constituents, diagnostics, market, features


# Compatibilité avec les pages existantes.
load_market_bundle = load_technical_bundle


def clear_live_market_caches() -> None:
    """Force uniquement le renouvellement des données de marché live."""
    for cached_function in (
        fetch_market_snapshot,
        _load_light_market_bundle_cached,
        _load_technical_bundle_cached,
    ):
        clear = getattr(cached_function, "clear", None)
        if callable(clear):
            clear()



def clear_universe_caches() -> None:
    """Force le renouvellement complet des données liées à l'univers actif."""
    clear_live_market_caches()
    try:
        from core.data import _load_constituents_cached

        clear = getattr(_load_constituents_cached, "clear", None)
        if callable(clear):
            clear()
    except Exception:
        pass
