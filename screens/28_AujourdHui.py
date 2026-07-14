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
    "Le brief quotidien Anatole : contexte, rotation, priorités, watchlist et prochaines actions.",
    "⚡",
)

ctx = current_context()


def _safe_float(value, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


def _fmt_pct(value, decimals: int = 2, signed: bool = True) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.{decimals}f} %".replace(".", ",")


def _fmt_num(value, decimals: int = 1) -> str:
    number = _safe_float(value)
    if np.isnan(number):
        return "N/D"
    return f"{number:,.{decimals}f}".replace(",", " ").replace(".", ",")


def _open_ticker_actions(row: pd.Series, key_prefix: str) -> None:
    ticker = str(row.get("Ticker", "")).strip()
    yahoo = str(row.get("YahooTicker", ticker)).strip() or ticker
    if ticker:
        st.session_state["selected_ticker"] = yahoo
        st.session_state["focus_ticker"] = yahoo
        st.session_state["screener_query"] = ticker
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Focus", width="stretch", key=f"{key_prefix}_focus_{ticker}"):
            st.switch_page("screens/14_Focus.py")
    with c2:
        if st.button("Terminal", width="stretch", key=f"{key_prefix}_terminal_{ticker}"):
            st.switch_page("screens/27_Terminal_Pro.py")
    with c3:
        if st.button("Insiders", width="stretch", key=f"{key_prefix}_insiders_{ticker}"):
            st.switch_page("screens/25_Insiders.py")
    with c4:
        if st.button("Alerte", width="stretch", key=f"{key_prefix}_alerts_{ticker}"):
            st.switch_page("screens/4_Alertes.py")


def _send_question(question: str, key: str) -> None:
    if st.button(question, key=key, width="stretch"):
        st.session_state["assistant_prefill_question"] = question
        st.switch_page("screens/13_Assistant.py")


with st.sidebar:
    st.markdown("### Brief quotidien")
    st.caption("Le point de départ pour savoir quoi analyser aujourd’hui.")
    if st.button("Actualiser les données", width="stretch", key="today_refresh"):
        clear_live_market_caches()
        st.rerun()
    st.divider()
    today_mode = st.radio(
        "Niveau de lecture",
        ["Essentiel", "Investisseur", "Comité"],
        index=1,
        horizontal=False,
        key="today_reading_mode",
    )

with st.spinner("Construction du brief Anatole…"):
    constituents, diagnostics, market, features = load_technical_bundle()

frame = features if isinstance(features, pd.DataFrame) and not features.empty else market
try:
    watchlist = get_watchlist(profile)
except Exception:
    watchlist = []
brief = build_today_brief(frame, watchlist)

st.caption(
    f"Univers actif : {diagnostics.get('universe_label', 'Marché canadien')} · "
    f"Couverture analysée : {brief.metrics.get('coverage', 0)} titres · "
    f"Mode : {today_mode}"
)

# --- Command center -------------------------------------------------------
st.markdown("## Command Center")
col_a, col_b, col_c, col_d, col_e = st.columns(5)
cards = brief.signal_cards or []
for col, card in zip([col_a, col_b, col_c, col_d, col_e], cards):
    with col:
        st.metric(card.get("titre", "Signal"), card.get("valeur", "N/D"), help=card.get("detail", ""))

if brief.market_narrative:
    st.info(brief.market_narrative)

# --- Navigation tabs ------------------------------------------------------
tab_brief, tab_priorities, tab_rotation, tab_watchlist, tab_assistant = st.tabs(
    ["Brief 5 min", "Radar priorités", "Rotation", "Watchlist", "Assistant"]
)

with tab_brief:
    st.markdown("### Si tu n’as que 5 minutes")
    for i, item in enumerate(brief.five_minute_plan, start=1):
        st.markdown(f"**{i}.** {item}")

    st.markdown("### Résumé exécutif")
    for item in brief.executive_summary:
        st.markdown(f"- {item}")

    st.markdown("### Agenda d’analyse")
    agenda_cols = st.columns(2)
    for idx, item in enumerate(brief.agenda):
        with agenda_cols[idx % 2]:
            st.write(f"• {item}")

    quick = st.columns(4)
    with quick[0]:
        if st.button("Ouvrir le cockpit", width="stretch", key="today_cockpit"):
            st.switch_page("screens/0_Accueil.py")
    with quick[1]:
        if st.button("Terminal Pro", width="stretch", key="today_terminal_main"):
            st.switch_page("screens/27_Terminal_Pro.py")
    with quick[2]:
        if st.button("Screener", width="stretch", key="today_screener_main"):
            st.switch_page("screens/1_Screener.py")
    with quick[3]:
        if st.button("Alertes", width="stretch", key="today_alerts_main"):
            st.switch_page("screens/4_Alertes.py")

with tab_priorities:
    st.markdown("### Dossiers à ouvrir en priorité")
    if brief.actions.empty:
        st.info("Aucun mouvement prioritaire détecté avec les données actuelles.")
    else:
        top = brief.actions.head(6).copy()
        for idx, row in top.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1.0, 2.5, 1.1, 1.3])
                with c1:
                    st.markdown(f"### {row.get('Ticker', 'N/D')}")
                    st.caption(str(row.get("Secteur", "")))
                with c2:
                    st.markdown(f"**{row.get('Nom', '')}**")
                    st.write(str(row.get("Pourquoi suivre", "à vérifier")))
                    st.caption(str(row.get("Rôle du jour", "Signal du jour")))
                with c3:
                    st.metric("Variation", _fmt_pct(row.get("Variation")))
                    st.metric("RSI", _fmt_num(row.get("RSI14")))
                with c4:
                    priority = _safe_float(row.get("Priorité"), 0)
                    st.metric("Priorité", f"{priority:.0f}/100")
                    st.progress(max(0, min(100, int(priority))) / 100)
                _open_ticker_actions(row, f"priority_{idx}")

        with st.expander("Voir le tableau complet du radar", expanded=False):
            cols = [c for c in ["Ticker", "Nom", "Secteur", "Variation", "RSI14", "VolumeRelatif", "Score Anatole", "Priorité", "Rôle du jour", "Pourquoi suivre"] if c in brief.actions.columns]
            st.dataframe(
                brief.actions[cols],
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

    left, right = st.columns(2)
    with left:
        st.markdown("### Opportunités à valider")
        if brief.positive_cases.empty:
            st.caption("Aucun dossier positif prioritaire détecté.")
        else:
            cols = [c for c in ["Ticker", "Secteur", "Variation", "Score Anatole", "Priorité", "Pourquoi suivre"] if c in brief.positive_cases.columns]
            st.dataframe(brief.positive_cases[cols], hide_index=True, width="stretch")
    with right:
        st.markdown("### Risques à surveiller")
        if brief.risk_cases.empty:
            st.caption("Aucun risque prioritaire détecté.")
        else:
            cols = [c for c in ["Ticker", "Secteur", "Variation", "RSI14", "Priorité", "Pourquoi suivre"] if c in brief.risk_cases.columns]
            st.dataframe(brief.risk_cases[cols], hide_index=True, width="stretch")

with tab_rotation:
    st.markdown("### Lecture sectorielle")
    for item in brief.sector_story:
        st.markdown(f"- {item}")

    if brief.sectors.empty:
        st.info("La rotation sectorielle n’est pas disponible avec les données actuelles.")
    else:
        display = brief.sectors.copy()
        st.dataframe(
            display.head(12),
            hide_index=True,
            width="stretch",
            column_config={
                "Variation moyenne": st.column_config.NumberColumn(format="%+.2f%%"),
                "Largeur": st.column_config.NumberColumn(format="%.0f%%"),
                "Contribution indicative": st.column_config.NumberColumn(format="%+.2f%%"),
            },
        )
        st.markdown("### Meilleurs et plus faibles titres")
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Leaders**")
            leader_cols = [c for c in ["Ticker", "Nom", "Secteur", "Variation"] if c in brief.leaders.columns]
            st.dataframe(brief.leaders[leader_cols], hide_index=True, width="stretch", column_config={"Variation": st.column_config.NumberColumn(format="%+.2f%%")})
        with c2:
            st.write("**Sous pression**")
            laggard_cols = [c for c in ["Ticker", "Nom", "Secteur", "Variation"] if c in brief.laggards.columns]
            st.dataframe(brief.laggards[laggard_cols], hide_index=True, width="stretch", column_config={"Variation": st.column_config.NumberColumn(format="%+.2f%%")})

with tab_watchlist:
    st.markdown("### Watchlist intelligente")
    if brief.watchlist.empty:
        st.info("Ajoute des titres à ta watchlist pour obtenir un suivi quotidien personnalisé.")
        if st.button("Ouvrir la watchlist", width="stretch", key="today_watchlist_empty"):
            st.switch_page("screens/9_Watchlist.py")
    else:
        st.success(f"{len(brief.watchlist)} titre(s) de ta watchlist ont été retrouvés dans l’univers actif.")
        for idx, row in brief.watchlist_alerts.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 2.2, 1])
                with c1:
                    st.markdown(f"### {row.get('Ticker', 'N/D')}")
                    st.caption(str(row.get("Secteur", "")))
                with c2:
                    st.write(str(row.get("Nom", "")))
                    st.caption(str(row.get("Lecture", "à vérifier")))
                with c3:
                    st.metric("Variation", _fmt_pct(row.get("Variation")))
                    st.metric("Priorité", f"{_safe_float(row.get('Priorité watchlist'), 0):.0f}/100")
                _open_ticker_actions(row, f"watch_{idx}")

        cols = [c for c in ["Ticker", "Nom", "Secteur", "Variation", "RSI14", "VolumeRelatif", "Score Anatole", "Priorité watchlist", "Lecture"] if c in brief.watchlist.columns]
        st.dataframe(
            brief.watchlist[cols],
            hide_index=True,
            width="stretch",
            column_config={
                "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
                "RSI14": st.column_config.NumberColumn(format="%.1f"),
                "VolumeRelatif": st.column_config.NumberColumn(format="%.2fx"),
                "Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
                "Priorité watchlist": st.column_config.ProgressColumn("Priorité", min_value=0, max_value=100, format="%.1f"),
            },
        )

with tab_assistant:
    st.markdown("### Questions puissantes à lancer maintenant")
    qcols = st.columns(2)
    for idx, question in enumerate(brief.next_questions):
        with qcols[idx % 2]:
            _send_question(question, f"today_question_{idx}")

    st.markdown("### Copier le brief")
    markdown = build_today_markdown(frame, watchlist)
    st.text_area("Brief prêt à partager", markdown, height=420, key="today_markdown_copy")

st.caption("Anatole priorise les analyses; il ne fournit pas de recommandation personnalisée d’achat ou de vente.")
footer()
