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

st.caption("Tape un symbole, un nom d'entreprise, un secteur ou une fonction.")
render_universal_search("page", profile=profile)

st.divider()
st.page_link("screens/0_Accueil.py", label="Retour au cockpit", icon="🏠", width="stretch")

footer()
