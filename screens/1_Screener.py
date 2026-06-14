from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.analytics import apply_screener_preset, technical_signal
from core.data import fetch_fundamentals
from core.runtime import load_market_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context

configure_page("Screener", "🔎")
apply_style()
profile = sidebar_context()
page_header(
    "Screener TSX 60",
    "Filtre les titres selon le momentum, la tendance, le RSI, le volume et, en option, les fondamentaux.",
    "🔎",
)

constituents, diagnostics, snapshot, features = load_market_bundle()
features = features.copy()
features["Signal"] = features.apply(technical_signal, axis=1)

st.info(
    "Les critères techniques sont disponibles immédiatement. Les fondamentaux sont mis en cache 24 heures, "
    "mais leur premier chargement peut prendre un peu plus de temps."
)

controls = st.columns([1.4, 1, 1, 1])
with controls[0]:
    preset = st.selectbox(
        "Filtre prédéfini",
        [
            "Tous",
            "Momentum haussier",
            "Actions survendues",
            "Cassures / volume",
            "Tendance long terme",
            "Dividendes élevés",
            "Valorisation faible",
        ],
    )
with controls[1]:
    load_fundamentals = st.checkbox("Charger les fondamentaux", value=False)
with controls[2]:
    min_change = st.number_input("Variation min. (%)", value=-20.0, step=0.5)
with controls[3]:
    max_change = st.number_input("Variation max. (%)", value=20.0, step=0.5)

if load_fundamentals:
    with st.spinner("Chargement des fondamentaux..."):
        fundamentals = fetch_fundamentals(tuple(features["YahooTicker"].tolist()))
    features = features.merge(fundamentals, on="YahooTicker", how="left")

sector_options = sorted(features["Secteur"].dropna().unique().tolist())
filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
with filter_col1:
    sectors = st.multiselect("Secteurs", sector_options, default=sector_options)
with filter_col2:
    rsi_range = st.slider("RSI 14", 0.0, 100.0, (0.0, 100.0), 1.0)
with filter_col3:
    min_relative_volume = st.slider("Volume relatif minimum", 0.0, 5.0, 0.0, 0.1)
with filter_col4:
    trend_filter = st.multiselect("Signal", ["Haussier", "Neutre", "Baissier"], default=["Haussier", "Neutre", "Baissier"])

extra_col1, extra_col2, extra_col3, extra_col4 = st.columns(4)
with extra_col1:
    above_sma50 = st.checkbox("Prix au-dessus SMA50")
with extra_col2:
    above_sma200 = st.checkbox("Prix au-dessus SMA200")
with extra_col3:
    min_momentum_1m = st.number_input("Momentum 1 mois min. (%)", value=-100.0, step=1.0)
with extra_col4:
    max_volatility = st.number_input("Volatilité max. (%)", value=200.0, step=5.0)

result = features[
    features["Secteur"].isin(sectors)
    & features["Variation"].between(min_change, max_change, inclusive="both")
    & features["RSI14"].between(rsi_range[0], rsi_range[1], inclusive="both")
    & (features["VolumeRelatif"].fillna(0) >= min_relative_volume)
    & features["Signal"].isin(trend_filter)
    & (features["Momentum1M"].fillna(-999) >= min_momentum_1m)
    & (features["Volatilite20"].fillna(0) <= max_volatility)
].copy()

if above_sma50:
    result = result[result["AboveSMA50"]]
if above_sma200:
    result = result[result["AboveSMA200"]]
if preset != "Tous":
    if preset in {"Dividendes élevés", "Valorisation faible"} and not load_fundamentals:
        st.warning("Active le chargement des fondamentaux pour ce filtre.")
    else:
        result = apply_screener_preset(result, preset)

if load_fundamentals:
    fund_col1, fund_col2, fund_col3 = st.columns(3)
    with fund_col1:
        pe_max = st.number_input("P/E maximum", value=100.0, min_value=0.0)
    with fund_col2:
        dividend_min = st.number_input("Dividende minimum (%)", value=0.0, min_value=0.0)
    with fund_col3:
        market_cap_min = st.number_input("Capitalisation min. (G$)", value=0.0, min_value=0.0)
    result = result[
        (result["PE"].isna() | (result["PE"] <= pe_max))
        & (result["DividendYield"].fillna(0) >= dividend_min)
        & (result["MarketCap"].fillna(0) >= market_cap_min * 1_000_000_000)
    ]

sort_options = {
    "Variation du jour": "Variation",
    "Momentum 1 mois": "Momentum1M",
    "Momentum 3 mois": "Momentum3M",
    "Volume relatif": "VolumeRelatif",
    "RSI": "RSI14",
    "Volatilité": "Volatilite20",
}
if load_fundamentals:
    sort_options.update({"P/E": "PE", "Dividende": "DividendYield", "Capitalisation": "MarketCap"})

sort_col1, sort_col2 = st.columns([2, 1])
with sort_col1:
    sort_label = st.selectbox("Trier par", list(sort_options))
with sort_col2:
    descending = st.toggle("Ordre décroissant", value=True)
result = result.sort_values(sort_options[sort_label], ascending=not descending, na_position="last")

st.metric("Titres correspondant aux critères", len(result))
base_columns = [
    "Ticker", "Nom", "Secteur", "Prix", "Variation", "RSI14", "Momentum1M",
    "Momentum3M", "VolumeRelatif", "Volatilite20", "DistanceHigh52", "Signal",
]
if load_fundamentals:
    base_columns += ["PE", "ForwardPE", "DividendYield", "MarketCap", "Beta"]
base_columns = [column for column in base_columns if column in result]

st.dataframe(
    result[base_columns],
    hide_index=True,
    width="stretch",
    height=620,
    column_config={
        "Prix": st.column_config.NumberColumn(format="$%.2f"),
        "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
        "RSI14": st.column_config.NumberColumn("RSI", format="%.1f"),
        "Momentum1M": st.column_config.NumberColumn("Mom. 1M", format="%+.2f%%"),
        "Momentum3M": st.column_config.NumberColumn("Mom. 3M", format="%+.2f%%"),
        "VolumeRelatif": st.column_config.NumberColumn("Vol. relatif", format="%.2fx"),
        "Volatilite20": st.column_config.NumberColumn("Volatilité", format="%.1f%%"),
        "DistanceHigh52": st.column_config.NumberColumn("Écart sommet 52s", format="%+.1f%%"),
        "DividendYield": st.column_config.NumberColumn("Dividende", format="%.2f%%"),
        "MarketCap": st.column_config.NumberColumn("Capitalisation", format="compact"),
    },
)

st.download_button(
    "Télécharger les résultats en CSV",
    data=result[base_columns].to_csv(index=False).encode("utf-8-sig"),
    file_name="screener_tsx60.csv",
    mime="text/csv",
)

footer()
