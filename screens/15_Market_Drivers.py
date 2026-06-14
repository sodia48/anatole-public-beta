from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from core.analytics import market_pulse
from core.runtime import load_market_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context

configure_page("Moteurs du marché", "🧭")
apply_style()
sidebar_context()
page_header(
    "Pourquoi le marché bouge ?",
    "Décomposition indicative des contributions sectorielles et des titres qui expliquent le mouvement du TSX 60.",
    "🧭",
)

with st.spinner("Calcul des contributions du marché..."):
    constituents, _, market, features = load_market_bundle()

if features.empty:
    st.error("Données insuffisantes.")
    footer()
    st.stop()

work = features.copy()
work["PoidsIndice"] = pd.to_numeric(work.get("PoidsIndice"), errors="coerce").fillna(0)
work["Variation"] = pd.to_numeric(work.get("Variation"), errors="coerce")
work["ContributionPoints"] = work["PoidsIndice"] * work["Variation"] / 100
pulse = market_pulse(work)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Mouvement pondéré indicatif", f"{pulse.get('weighted_change', np.nan):+.2f}%")
m2.metric("Meilleur secteur", pulse.get("best_sector", "N/D"), f"{pulse.get('best_sector_change', np.nan):+.2f}%")
m3.metric("Secteur le plus faible", pulse.get("worst_sector", "N/D"), f"{pulse.get('worst_sector_change', np.nan):+.2f}%")
m4.metric("Ratio hausses / baisses", f"{pulse.get('advancers', 0)} / {pulse.get('decliners', 0)}")

sector = (
    work.groupby("Secteur", as_index=False)
    .agg(ContributionPoints=("ContributionPoints", "sum"), VariationMoyenne=("Variation", "mean"), Poids=("PoidsIndice", "sum"))
    .sort_values("ContributionPoints")
)

fig = px.bar(
    sector,
    x="ContributionPoints",
    y="Secteur",
    orientation="h",
    color="ContributionPoints",
    color_continuous_scale=["#DC2626", "#315A7D", "#059669"],
    color_continuous_midpoint=0,
    title="Contribution sectorielle indicative au mouvement",
    labels={"ContributionPoints": "Contribution (points de % indicatifs)"},
)
fig.update_layout(height=520, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,.55)")
st.plotly_chart(fig, width="stretch", key="market_drivers_contribution")

left, right = st.columns(2)
with left:
    st.subheader("Principaux moteurs positifs")
    positive = work.nlargest(12, "ContributionPoints")[["Ticker", "Nom", "Secteur", "Variation", "PoidsIndice", "ContributionPoints"]]
    st.dataframe(positive, hide_index=True, width="stretch", column_config={
        "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
        "PoidsIndice": st.column_config.NumberColumn(format="%.2f%%"),
        "ContributionPoints": st.column_config.NumberColumn(format="%+.3f"),
    })
with right:
    st.subheader("Principaux freins")
    negative = work.nsmallest(12, "ContributionPoints")[["Ticker", "Nom", "Secteur", "Variation", "PoidsIndice", "ContributionPoints"]]
    st.dataframe(negative, hide_index=True, width="stretch", column_config={
        "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
        "PoidsIndice": st.column_config.NumberColumn(format="%.2f%%"),
        "ContributionPoints": st.column_config.NumberColumn(format="%+.3f"),
    })

st.warning("Cette décomposition est une approximation fondée sur les poids disponibles et les variations observées. Elle n'établit pas une causalité économique certaine.")
footer()
