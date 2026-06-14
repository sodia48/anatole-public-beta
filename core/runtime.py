from __future__ import annotations

import pandas as pd
import streamlit as st

from core.analytics import build_feature_table
from core.data import fetch_batch_history, fetch_market_snapshot, load_constituents


@st.cache_data(ttl=60, show_spinner=False)
def load_light_market_bundle() -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Chargement léger utilisé par le cockpit : composition + snapshot uniquement."""
    constituents, diagnostics = load_constituents()
    tickers = tuple(constituents["YahooTicker"].tolist())
    snapshot = fetch_market_snapshot(tickers)
    market = constituents.merge(snapshot, on="YahooTicker", how="left")
    return constituents, diagnostics, market


@st.cache_data(ttl=1_800, show_spinner=False)
def load_technical_bundle() -> tuple[pd.DataFrame, dict, pd.DataFrame, pd.DataFrame]:
    """Chargement technique plus lourd, exécuté seulement sur demande."""
    constituents, diagnostics, market = load_light_market_bundle()
    tickers = tuple(constituents["YahooTicker"].tolist())
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
    snapshot = market[snapshot_columns].copy()
    features = build_feature_table(constituents, histories, snapshot)
    return constituents, diagnostics, market, features


# Compatibilité avec les pages existantes.
load_market_bundle = load_technical_bundle
