from __future__ import annotations

import streamlit as st

from core.database import database_backend, database_health
from core.public_beta import auth_configured, current_context
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("État de la bêta", "🧪")
apply_style()
sidebar_context()
context = current_context()

page_header(
    "État de la bêta publique",
    "Transparence sur les fonctions disponibles, les limites de la bêta et la qualité des données.",
    "🧪",
)

db_ok, db_detail = database_health()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Version", "4.7 Smooth Audit")
c2.metric("Sauvegarde", "Active" if db_ok else "À vérifier")
c3.metric("Données utilisateur", "Disponibles" if db_ok else "À vérifier")
c4.metric("Connexion", "Active" if auth_configured() else "Mode invité")

if not db_ok:
    st.error("La sauvegarde des données utilisateur est temporairement indisponible.")

st.markdown(
    """
    ### Fonctions en bêta

    - Cotations et historiques de marché
    - Heatmap et screener
    - Calendrier économique officiel
    - Portefeuille et watchlist de démonstration
    - Alertes et notifications
    - Rapports PDF/Excel
    - Assistant contextuel optionnel

    ### Limites connues

    - Les données Yahoo Finance peuvent être différées ou limitées.
    - Certaines sources officielles peuvent changer leur format.
    - Le mode invité n’offre pas une persistance garantie.
    - L’application n’est pas un service de courtage.

    ### Optimisations actives

    - Cotations live avec dernier snapshot valide en secours
    - Calendriers officiels chargés en parallèle
    - Actualités et calendriers d’entreprises chargés en parallèle
    - Pages lourdes chargées seulement à la demande
    - Préférences chargées rapidement
    - Vérifications automatiques des pages principales
    """
)

if context.authenticated:
    st.success("Votre session est authentifiée et isolée.")
else:
    st.info("Vous utilisez une session invitée temporaire.")

footer()
