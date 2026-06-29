from __future__ import annotations

import streamlit as st

from core.analytics import portfolio_table
from core.database import get_notifications, get_positions
from core.rate_limit import consume
from core.reports import market_pdf_bytes, portfolio_excel_bytes
from core.runtime import load_light_market_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("Rapports", "📄")
apply_style()
profile = sidebar_context()
page_header(
    "Rapports",
    "Prépare un PDF de synthèse ou un classeur Excel seulement lorsque tu en as besoin.",
)

report_title = st.text_input("Titre du rapport", value="Rapport Anatole - Univers actif")
notes = st.text_area("Commentaire d'introduction", placeholder="Ex. Résumé hebdomadaire du marché et de mon portefeuille.")

if st.button("Préparer les rapports", type="primary", width="stretch"):
    allowed, wait_seconds = consume(
        "generate_reports",
        max_calls=3,
        window_seconds=600,
    )
    if allowed:
        st.session_state.reports_ready = True
    else:
        st.warning(
            f"Limite de génération atteinte. Réessaie dans environ {wait_seconds} secondes."
        )

if st.session_state.get("reports_ready"):
    with st.spinner("Préparation des données…"):
        constituents, _, market = load_light_market_bundle()
        positions = get_positions(profile)
        portfolio = portfolio_table(positions, market, constituents)
        notifications = get_notifications(profile, limit=100)

    c1, c2, c3 = st.columns(3)
    c1.metric("Titres couverts", len(market))
    c2.metric("Positions", len(portfolio))
    c3.metric("Notifications", len(notifications))

    with st.expander("Aperçu", expanded=False):
        st.dataframe(market.head(25), hide_index=True, width="stretch")
        if not portfolio.empty:
            st.dataframe(portfolio, hide_index=True, width="stretch")

    with st.spinner("Génération des fichiers…"):
        pdf_bytes = market_pdf_bytes(report_title, market, portfolio, notifications, notes)
        excel_bytes = portfolio_excel_bytes(report_title, market, portfolio, notifications)

    left, right = st.columns(2)
    with left:
        st.download_button(
            "Télécharger le PDF",
            data=pdf_bytes,
            file_name="rapport_anatole.pdf",
            mime="application/pdf",
            width="stretch",
            type="primary",
        )
    with right:
        st.download_button(
            "Télécharger le fichier Excel",
            data=excel_bytes,
            file_name="rapport_anatole.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
else:
    st.info("Aucune donnée lourde n'est chargée avant que tu demandes la préparation du rapport.")

footer()
