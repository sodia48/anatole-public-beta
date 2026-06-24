from __future__ import annotations

import streamlit as st

from core.analytics import normalize_prices, return_statistics
from core.charts import correlation_chart, normalized_performance_chart
from core.data import fetch_batch_history, fetch_fundamentals, load_constituents
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context

configure_page("Comparateur", "⚖️")
apply_style()
profile = sidebar_context()
page_header(
    "Comparateur d'actions",
    "Compare jusqu'à cinq titres sur une base 100, leurs risques, leurs corrélations et leurs fondamentaux.",
    "⚖️",
)

constituents, diagnostics = load_constituents()
lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))
period = st.selectbox("Période", ["6mo", "1y", "2y", "5y", "10y"], index=2)
session_defaults = st.session_state.pop("comparison_tickers", None)
base_defaults = session_defaults if session_defaults else ["RY.TO", "TD.TO", "SHOP.TO"]
defaults = [ticker for ticker in base_defaults if ticker in lookup]
selected = st.multiselect(
    "Titres à comparer (2 à 5)",
    constituents["YahooTicker"].tolist(),
    default=defaults,
    max_selections=5,
    format_func=lambda value: lookup.get(value, value),
)

if len(selected) < 2:
    st.info("Sélectionne au moins deux titres.")
    footer()
    st.stop()

with st.spinner("Téléchargement des historiques..."):
    histories = fetch_batch_history(tuple(selected), period, "1d")
normalized = normalize_prices(histories)
if normalized.empty:
    st.error("Historique indisponible pour la sélection.")
    footer()
    st.stop()

st.plotly_chart(normalized_performance_chart(normalized), width="stretch", key="comparateur_performance_normalisee")
st.subheader("Statistiques de rendement et de risque")
stats = return_statistics(normalized)
st.dataframe(
    stats,
    hide_index=True,
    width="stretch",
    column_config={
        "Rendement total (%)": st.column_config.NumberColumn(format="%+.2f%%"),
        "Rendement annualisé (%)": st.column_config.NumberColumn(format="%+.2f%%"),
        "Volatilité (%)": st.column_config.NumberColumn(format="%.2f%%"),
        "Sharpe": st.column_config.NumberColumn(format="%.2f"),
        "Drawdown max (%)": st.column_config.NumberColumn(format="%.2f%%"),
    },
)

returns = normalized.pct_change().dropna()
st.plotly_chart(correlation_chart(returns.corr()), width="stretch", key="comparateur_correlation")

if st.checkbox("Charger la comparaison fondamentale", value=False):
    with st.spinner("Chargement des fondamentaux..."):
        fundamentals = fetch_fundamentals(tuple(selected))
    names = constituents[["YahooTicker", "Ticker", "Nom", "Secteur"]]
    fundamentals = names.merge(fundamentals, on="YahooTicker", how="right")
    st.subheader("Comparaison fondamentale")
    st.dataframe(
        fundamentals,
        hide_index=True,
        width="stretch",
        column_config={
            "MarketCap": st.column_config.NumberColumn("Capitalisation", format="compact"),
            "PE": st.column_config.NumberColumn("P/E", format="%.2f"),
            "ForwardPE": st.column_config.NumberColumn("P/E anticipé", format="%.2f"),
            "DividendYield": st.column_config.NumberColumn("Dividende", format="%.2f%%"),
            "ProfitMargin": st.column_config.NumberColumn("Marge", format="%.2f%%"),
            "RevenueGrowth": st.column_config.NumberColumn("Croissance CA", format="%+.2f%%"),
        },
    )

footer()
