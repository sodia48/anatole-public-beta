from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.runtime import load_light_market_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context, render_mobile_watchlist_cards, skeleton_cards
from core.universe import current_universe
from core.utils import format_money, safe_float

configure_page("Aujourd'hui", "📱")
apply_style()
profile = sidebar_context()
page_header(
    "Aujourd'hui",
    "La vue mobile la plus rapide : marché maintenant, gagnants, perdants, secteurs et titres à surveiller.",
    "📱",
)

placeholder = st.empty()
with placeholder.container():
    skeleton_cards(4, 84)

_, diagnostics, market = load_light_market_bundle()
placeholder.empty()

if market.empty:
    st.warning("Les données du marché sont temporairement indisponibles.")
    footer()
    st.stop()

market = market.copy()
market["Variation"] = pd.to_numeric(market.get("Variation"), errors="coerce")
market["Prix"] = pd.to_numeric(market.get("Prix"), errors="coerce")
valid = market.dropna(subset=["Variation"]).copy()

advancers = int((valid["Variation"] > 0).sum())
decliners = int((valid["Variation"] < 0).sum())
weighted = float(valid["Variation"].mean()) if not valid.empty else np.nan
sector = valid.groupby("Secteur", as_index=False)["Variation"].mean().sort_values("Variation", ascending=False)
best_sector = sector.iloc[0] if not sector.empty else {"Secteur": "N/D", "Variation": np.nan}
worst_sector = sector.iloc[-1] if not sector.empty else {"Secteur": "N/D", "Variation": np.nan}

top_gainers = valid.nlargest(5, "Variation")
top_losers = valid.nsmallest(5, "Variation")
watch = pd.concat([top_gainers.head(3), top_losers.head(2)], ignore_index=True).drop_duplicates(subset=["YahooTicker"])

st.markdown("#### Marché maintenant")
col1, col2, col3 = st.columns(3)
col1.metric(current_universe().short_label, f"{weighted:+.2f}%" if not np.isnan(weighted) else "N/D")
col2.metric("En hausse", advancers)
col3.metric("En baisse", decliners)

with st.container(border=True):
    st.markdown("#### Résumé ultra-rapide")
    st.write(f"• {current_universe().short_label} évolue à {weighted:+.2f}% avec {advancers} titres en hausse et {decliners} en baisse.")
    st.write(f"• Le secteur le plus fort est {best_sector['Secteur']} ({safe_float(best_sector['Variation']):+.2f}%).")
    st.write(f"• La zone la plus fragile est {worst_sector['Secteur']} ({safe_float(worst_sector['Variation']):+.2f}%).")

st.markdown("#### Titres à surveiller")
render_mobile_watchlist_cards(
    [
        {
            "Ticker": row.get("Ticker"),
            "Nom": row.get("Nom"),
            "Secteur": row.get("Secteur"),
            "Prix": format_money(row.get("Prix")),
            "Variation": row.get("Variation"),
            "Volume": row.get("Volume"),
        }
        for _, row in watch.iterrows()
    ]
)

left, right = st.columns(2)
with left:
    st.markdown("#### Top gagnants")
    st.dataframe(
        top_gainers[[col for col in ["Ticker", "Prix", "Variation", "Secteur"] if col in top_gainers]],
        hide_index=True,
        width="stretch",
    )
with right:
    st.markdown("#### Top perdants")
    st.dataframe(
        top_losers[[col for col in ["Ticker", "Prix", "Variation", "Secteur"] if col in top_losers]],
        hide_index=True,
        width="stretch",
    )

with st.expander("Secteurs forts et faibles", expanded=False):
    st.dataframe(sector.head(10), hide_index=True, width="stretch")

st.caption(
    f"Univers actif : {diagnostics.get('universe_label', current_universe().label)} · "
    f"{len(valid)} titres avec variation disponible."
)

footer()
