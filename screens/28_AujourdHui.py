from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.database import get_watchlist
from core.public_beta import current_context
from core.retention_engine import build_today_brief, build_today_markdown
from core.runtime import clear_live_market_caches, load_technical_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("Aujourd’hui", "⚡")
apply_style()
profile = sidebar_context()
page_header(
    "Aujourd’hui sur le marché",
    "Le brief quotidien qui transforme le bruit du marché en priorités d’analyse.",
    "Rétention · Lecture quotidienne",
)

ctx = current_context()

with st.sidebar:
    st.markdown("### Brief quotidien")
    st.caption("Ouvre cette page chaque matin pour voir ce qui mérite ton attention.")
    if st.button("Actualiser les données", width="stretch", key="today_refresh"):
        clear_live_market_caches()
        st.rerun()

with st.spinner("Construction du brief Anatole…"):
    constituents, diagnostics, market, features = load_technical_bundle()

frame = features if isinstance(features, pd.DataFrame) and not features.empty else market
watchlist = get_watchlist(profile)
brief = build_today_brief(frame, watchlist)

st.caption(
    f"Univers actif : {diagnostics.get('universe_label', 'Marché canadien')} · "
    f"Couverture analysée : {brief.metrics.get('coverage', 0)} titres · "
    "Bêta publique"
)

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Régime", brief.market_label)
with m2:
    breadth = brief.metrics.get("breadth")
    st.metric("Largeur", "N/D" if breadth is None or np.isnan(float(breadth)) else f"{float(breadth):.0f} %")
with m3:
    weighted = brief.metrics.get("weighted_change")
    st.metric("Mouvement pondéré", "N/D" if weighted is None or np.isnan(float(weighted)) else f"{float(weighted):+.2f} %")
with m4:
    st.metric("Titres suivis", len(watchlist))

st.markdown("### Résumé exécutif")
for item in brief.executive_summary:
    st.markdown(f"- {item}")

left, right = st.columns([1.05, 0.95])
with left:
    st.markdown("### Rotation sectorielle")
    if brief.sectors.empty:
        st.info("La rotation sectorielle n’est pas disponible avec les données actuelles.")
    else:
        st.dataframe(
            brief.sectors.head(12),
            hide_index=True,
            width="stretch",
            column_config={
                "Variation moyenne": st.column_config.NumberColumn(format="%+.2f%%"),
                "Largeur": st.column_config.NumberColumn(format="%.0f%%"),
            },
        )

with right:
    st.markdown("### Points à vérifier")
    for item in brief.watch_items:
        st.markdown(f"- {item}")
    st.markdown("### Questions rapides")
    for idx, question in enumerate(brief.next_questions[:5]):
        if st.button(question, key=f"today_question_{idx}", width="stretch"):
            st.session_state["assistant_prefill_question"] = question
            try:
                st.switch_page("screens/13_Assistant.py")
            except Exception:
                st.info("Question mémorisée. Ouvre l’assistant contextuel pour continuer.")

st.markdown("### Titres qui méritent une vérification")
if brief.actions.empty:
    st.info("Aucun mouvement prioritaire détecté avec les données actuelles.")
else:
    action_cols = [c for c in ["Ticker", "Nom", "Secteur", "Variation", "RSI14", "VolumeRelatif", "Score Anatole", "Priorité", "Pourquoi suivre"] if c in brief.actions.columns]
    st.dataframe(
        brief.actions[action_cols],
        hide_index=True,
        width="stretch",
        column_config={
            "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
            "RSI14": st.column_config.NumberColumn(format="%.1f"),
            "VolumeRelatif": st.column_config.NumberColumn(format="%.2fx"),
            "Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            "Priorité": st.column_config.ProgressColumn("Priorité", min_value=0, max_value=100, format="%.1f"),
        },
    )
    selected = st.selectbox(
        "Approfondir un titre",
        brief.actions["Ticker"].head(40).tolist(),
        index=None,
        placeholder="Choisir un titre du brief…",
        key="today_open_ticker",
    )
    if selected:
        row = brief.actions.loc[brief.actions["Ticker"] == selected].iloc[0]
        yahoo = str(row.get("YahooTicker", selected))
        st.session_state["selected_ticker"] = yahoo
        st.session_state["focus_ticker"] = yahoo
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("Ouvrir Focus", width="stretch", key="today_to_focus"):
                st.switch_page("screens/14_Focus.py")
        with c2:
            if st.button("Voir Insiders", width="stretch", key="today_to_insiders"):
                st.switch_page("screens/25_Insiders.py")
        with c3:
            if st.button("Créer alerte", width="stretch", key="today_to_alerts"):
                st.switch_page("screens/4_Alertes.py")
        with c4:
            if st.button("Terminal Pro", width="stretch", key="today_to_terminal"):
                st.switch_page("screens/27_Terminal_Pro.py")

st.markdown("### Watchlist intelligente")
if brief.watchlist.empty:
    st.info("Ajoute des titres à ta watchlist pour obtenir un suivi quotidien personnalisé.")
else:
    cols = [c for c in ["Ticker", "Nom", "Secteur", "Variation", "RSI14", "VolumeRelatif", "Score Anatole"] if c in brief.watchlist.columns]
    st.dataframe(
        brief.watchlist[cols],
        hide_index=True,
        width="stretch",
        column_config={
            "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
            "RSI14": st.column_config.NumberColumn(format="%.1f"),
            "VolumeRelatif": st.column_config.NumberColumn(format="%.2fx"),
            "Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        },
    )

with st.expander("Copier le brief du jour", expanded=False):
    st.markdown(build_today_markdown(frame, watchlist))

st.caption("Anatole priorise les analyses; il ne fournit pas de recommandation personnalisée d’achat ou de vente.")
footer()
