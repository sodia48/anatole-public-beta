from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.analytics import normalize_prices
from core.charts import correlation_chart, rolling_correlation_chart
from core.data import fetch_batch_history, load_constituents
from core.database import get_positions, get_watchlist
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context

configure_page("Corrélations", "🧩")
apply_style()
profile = sidebar_context()
page_header(
    "Corrélations et diversification",
    "Mesure les relations entre titres et observe leur stabilité dans le temps.",
    "🧩",
)

constituents, diagnostics = load_constituents()
lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))
watchlist = [ticker for ticker in get_watchlist(profile) if ticker in lookup]
positions = get_positions(profile)
portfolio_tickers = positions["ticker"].tolist() if not positions.empty else []
defaults = list(dict.fromkeys((portfolio_tickers + watchlist + ["RY.TO", "SHOP.TO"])))[0:6]
defaults = [ticker for ticker in defaults if ticker in lookup]

period = st.selectbox("Période", ["6mo", "1y", "2y", "5y"], index=2)
selected = st.multiselect(
    "Titres (2 à 15)",
    constituents["YahooTicker"].tolist(),
    default=defaults,
    max_selections=15,
    format_func=lambda value: lookup.get(value, value),
)

if len(selected) < 2:
    st.info("Sélectionne au moins deux titres.")
    footer()
    st.stop()

histories = fetch_batch_history(tuple(selected), period, "1d")
normalized = normalize_prices(histories)
if normalized.empty:
    st.error("Historique indisponible.")
    footer()
    st.stop()

returns = normalized.pct_change().dropna()
correlation = returns.corr()
st.plotly_chart(correlation_chart(correlation), width="stretch", key="correlations_matrice")

upper = correlation.where(pd.DataFrame(1, index=correlation.index, columns=correlation.columns).astype(bool))
pairs = []
for i, first in enumerate(correlation.columns):
    for second in correlation.columns[i + 1:]:
        pairs.append({"Titre 1": first, "Titre 2": second, "Corrélation": correlation.loc[first, second]})
pairs_df = pd.DataFrame(pairs).sort_values("Corrélation", ascending=False)

p1, p2 = st.columns(2)
with p1:
    st.subheader("Paires les plus corrélées")
    st.dataframe(pairs_df.head(10), hide_index=True, width="stretch", column_config={"Corrélation": st.column_config.NumberColumn(format="%.2f")})
with p2:
    st.subheader("Paires les moins corrélées")
    st.dataframe(pairs_df.tail(10).sort_values("Corrélation"), hide_index=True, width="stretch", column_config={"Corrélation": st.column_config.NumberColumn(format="%.2f")})

st.subheader("Corrélation mobile")
r1, r2, r3 = st.columns(3)
with r1:
    first = st.selectbox("Premier titre", selected, index=0)
with r2:
    second_options = [ticker for ticker in selected if ticker != first]
    second = st.selectbox("Deuxième titre", second_options, index=0)
with r3:
    window = st.select_slider("Fenêtre", [20, 40, 60, 90, 120, 252], value=60)
st.plotly_chart(rolling_correlation_chart(normalized, first, second, window), width="stretch", key=f"correlations_mobile_{first}_{second}_{window}")

average_abs_corr = correlation.where(~pd.DataFrame(np.eye(len(correlation), dtype=bool), index=correlation.index, columns=correlation.columns)).abs().stack().mean()
st.metric("Corrélation absolue moyenne", f"{average_abs_corr:.2f}", help="Plus elle est faible, plus la diversification entre les titres est généralement élevée.")

footer()
