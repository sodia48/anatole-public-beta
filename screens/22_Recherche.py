from __future__ import annotations

import streamlit as st

from core.search import render_universal_search
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("Recherche", "🔍")
apply_style()
profile = sidebar_context()
page_header(
    "Recherche",
    "Trouve rapidement un titre, une page ou une commande Anatole.",
    "🔍",
)

st.caption("Tape un symbole, un nom d'entreprise, un secteur ou une fonction. Anatole mémorise aussi tes recherches récentes sur mobile.")
render_universal_search("page", profile=profile)

st.divider()
links = st.columns(2)
links[0].page_link("screens/0_Accueil.py", label="Retour au cockpit", icon="🏠", width="stretch")
links[1].page_link("screens/23_Aujourd_hui.py", label="Vue Aujourd'hui", icon="📱", width="stretch")

footer()
