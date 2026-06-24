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
    return constituents, diagnostics, market


def load_light_market_bundle() -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """API compatible avec les pages existantes, avec garde Render Free."""
    key = current_universe_key()
    try:
        return _load_light_market_bundle_cached(key)
    except Exception as exc:
        logging.exception("Échec de l'univers %s, retour TSX 60.", key)
        if key != DEFAULT_UNIVERSE_KEY:
            constituents, diagnostics, market = _load_light_market_bundle_cached(
                DEFAULT_UNIVERSE_KEY
            )
            diagnostics = dict(diagnostics)
            diagnostics["status"] = "Fallback TSX 60"
            diagnostics["error"] = (
                f"L'univers demandé ({key}) était temporairement trop lourd "
                f"ou indisponible : {type(exc).__name__}."
            )
            return constituents, diagnostics, market
        raise


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
        logging.exception("Échec technique de l'univers %s, retour TSX 60.", key)
        if key != DEFAULT_UNIVERSE_KEY:
            constituents, diagnostics, market, features = _load_technical_bundle_cached(
                DEFAULT_UNIVERSE_KEY
            )
            diagnostics = dict(diagnostics)
            diagnostics["status"] = "Fallback TSX 60"
            diagnostics["error"] = (
                f"L'univers demandé ({key}) était temporairement trop lourd "
                f"ou indisponible : {type(exc).__name__}."
            )
            return constituents, diagnostics, market, features
        raise


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
