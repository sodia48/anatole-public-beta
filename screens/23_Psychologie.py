from __future__ import annotations

import streamlit as st

from core.data_quality import render_data_quality_strip
from core.market_psychology import (
    market_psychology_score,
    psychology_components_frame,
    psychology_gauge_figure,
    psychology_summary_text,
)
from core.performance import load_timer, perf_caption
from core.runtime import load_light_market_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.universe import current_universe

configure_page("Psychologie du marché", "🧠")
apply_style()
sidebar_context()
page_header(
    "Psychologie du marché",
    "Un indicateur psychologique interne, inspiré du principe Fear & Greed, calculé à partir des données Anatole.",
    "🧠",
)

with st.spinner("Lecture du pouls psychologique du marché…"):
    with load_timer("market_psychology"):
        constituents, diagnostics, market = load_light_market_bundle()
perf_caption("market_psychology", threshold=2.0)

if market.empty:
    st.warning("Les données de marché sont temporairement indisponibles.")
    footer()
    st.stop()

render_data_quality_strip(market, diagnostics, compact=True)

result = market_psychology_score(market)
score = float(result["score"])
label = str(result["label"])

left, right = st.columns([1.2, 1])
with left:
    st.plotly_chart(psychology_gauge_figure(score, label), width="stretch", key="market_psychology_gauge")
with right:
    st.metric("Indice psychologique", f"{score:.1f}/100", label)
    st.write(psychology_summary_text(result))
    st.caption(
        "Ce n'est pas le CNN Fear & Greed Index officiel. "
        "C'est une lecture propriétaire Anatole basée sur la largeur du marché, le momentum, les volumes, la tendance et la dispersion sectorielle."
    )

st.subheader("Composantes")
components = psychology_components_frame(result)
st.dataframe(
    components,
    hide_index=True,
    width="stretch",
    column_config={
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
    },
)

st.subheader("Lecture rapide")
if score < 40:
    st.warning(
        "La psychologie est défensive. Surveille les titres solides qui résistent mieux que le marché, "
        "les secteurs refuges et les niveaux de support."
    )
elif score > 80:
    st.info("L'optimisme est très élevé. Le momentum peut rester fort, mais le risque d'excès augmente.")
else:
    st.success(
        "La psychologie est constructive ou équilibrée. Compare le score avec la tendance technique et les moteurs sectoriels."
    )

st.caption(f"Univers analysé : {current_universe().label} · {len(market)} titres suivis.")

footer()
