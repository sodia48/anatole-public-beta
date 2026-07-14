from __future__ import annotations

import streamlit as st

from core.preferences import load_preferences, save_preferences
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("Préférences", "⚙️")
apply_style()
profile = sidebar_context()
page_header(
    "Préférences",
    "Choisis une interface sobre, la densité des informations et le comportement des données live.",
)

prefs = load_preferences(profile)

with st.form("preferences_form"):
    st.subheader("Interface")
    c1, c2, c3 = st.columns(3)
    with c1:
        theme = st.selectbox("Thème", ["light", "dark"], index=0 if prefs["theme"] == "light" else 1, format_func=lambda x: "Bleu ciel" if x == "light" else "Sombre")
    with c2:
        density = st.selectbox("Densité", ["comfortable", "compact"], index=0 if prefs["density"] == "comfortable" else 1, format_func=lambda x: "Confortable" if x == "comfortable" else "Compacte")
    with c3:
        experience = st.selectbox("Niveau d'information", ["simple", "advanced"], index=0 if prefs["experience_mode"] == "simple" else 1, format_func=lambda x: "Essentiel" if x == "simple" else "Avancé")

    st.subheader("Éléments facultatifs")
    c4, c5 = st.columns(2)
    with c4:
        show_ticker = st.checkbox("Afficher le ruban de cotations", value=prefs["show_ticker"] == "true")
        show_quick_links = st.checkbox("Afficher les raccourcis sur l'accueil", value=prefs["show_quick_links"] == "true")
        show_animations = st.checkbox("Activer les animations", value=prefs["show_animations"] == "true")
    with c5:
        show_advanced_home = st.checkbox("Charger l'analyse technique sur l'accueil", value=prefs["show_advanced_home"] == "true")
        show_mobile_nav = st.checkbox("Afficher la navigation mobile", value=prefs["show_mobile_nav"] != "false")
        show_event_markers = st.checkbox("Afficher les événements sur le graphique Focus", value=prefs["show_event_markers"] == "true")
        st.caption("Les indicateurs Plotly du Mode Focus sont maintenant automatiques et ne nécessitent plus d’activation.")

    st.subheader("Données")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        default_period = st.selectbox("Période par défaut", ["3mo", "6mo", "1y", "2y", "5y"], index=["3mo", "6mo", "1y", "2y", "5y"].index(prefs.get("default_period", "1y")))
    with d2:
        decimal_places = st.selectbox("Décimales", [0, 1, 2, 3], index=[0, 1, 2, 3].index(int(prefs.get("decimal_places", "2"))))
    with d3:
        refresh_seconds = st.selectbox("Actualisation", [30, 60, 120, 300], index=[30, 60, 120, 300].index(int(prefs.get("refresh_seconds", "60"))))
    with d4:
        refresh_only_open = st.checkbox("Actualiser automatiquement seulement lorsque le marché est ouvert", value=prefs["refresh_only_market_open"] != "false")

    submitted = st.form_submit_button("Enregistrer", type="primary", width="stretch")

if submitted:
    values = {
        "theme": theme,
        "density": density,
        "experience_mode": experience,
        "show_ticker": show_ticker,
        "show_quick_links": show_quick_links,
        "show_animations": show_animations,
        "show_advanced_home": show_advanced_home,
        "show_mobile_nav": show_mobile_nav,
        "show_event_markers": show_event_markers,
        "default_period": default_period,
        "decimal_places": decimal_places,
        "refresh_seconds": refresh_seconds,
        "refresh_only_market_open": refresh_only_open,
    }
    save_preferences(profile, values)
    st.session_state["theme_toggle"] = theme == "dark"
    st.session_state["compact_toggle"] = density == "compact"
    st.session_state["_anatole_theme"] = theme
    try:
        st.query_params["anatole_theme"] = theme
    except Exception:
        pass
    st.session_state.pop("_preferences_profile", None)
    st.success("Préférences enregistrées.")
    st.rerun()

st.caption("Le mode essentiel masque les analyses coûteuses jusqu'à ce que tu les demandes. Cela accélère nettement l'accueil.")
footer()
