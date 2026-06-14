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
    "Transparence sur les fonctions, les limites et la configuration active.",
    "🧪",
)

db_ok, db_detail = database_health()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Version", "4.6 Public Beta")
c2.metric("Base", database_backend())
c3.metric("Base disponible", "Oui" if db_ok else "Non")
c4.metric("Connexion OIDC", "Configurée" if auth_configured() else "Non configurée")

if not db_ok:
    st.error(f"Base de données indisponible : {db_detail}")

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
    - Le worker d’alertes doit être déployé séparément pour les notifications hors session.
    - L’application n’est pas un service de courtage.
    """
)

if context.authenticated:
    st.success("Votre session est authentifiée et isolée.")
else:
    st.info("Vous utilisez une session invitée temporaire.")

footer()
