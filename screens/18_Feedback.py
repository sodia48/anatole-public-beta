from __future__ import annotations

import streamlit as st

from core.database import add_feedback, get_feedback
from core.public_beta import current_context
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("Votre avis", "💬")
apply_style()
profile = sidebar_context()
context = current_context()

page_header(
    "Votre avis sur Anatole",
    "Aide-nous à prioriser les corrections et les fonctionnalités de la bêta publique.",
    "💬",
)

with st.form("beta_feedback_form", clear_on_submit=True):
    rating = st.slider("Satisfaction générale", 1, 5, 4)
    category = st.selectbox(
        "Catégorie",
        [
            "Bug",
            "Performance",
            "Données",
            "Design",
            "Fonctionnalité",
            "Accessibilité",
            "Général",
        ],
    )
    page_name = st.text_input(
        "Page concernée",
        placeholder="Ex. Cockpit, Calendrier, Portefeuille…",
    )
    message = st.text_area(
        "Votre commentaire",
        placeholder="Décris précisément le problème ou l’amélioration souhaitée.",
        max_chars=3000,
    )
    contact = st.text_input(
        "Courriel de suivi facultatif",
        value=context.email,
    )

    submitted = st.form_submit_button(
        "Envoyer le commentaire",
        type="primary",
        use_container_width=True,
    )

if submitted:
    if len(message.strip()) < 10:
        st.error("Le commentaire doit contenir au moins 10 caractères.")
    else:
        add_feedback(
            profile=profile,
            rating=rating,
            category=category,
            message=message,
            page_name=page_name,
            contact_email=contact,
        )
        st.success("Merci. Votre commentaire a été enregistré.")

if context.is_admin:
    st.divider()
    st.subheader("Commentaires récents — administration")
    feedback = get_feedback(limit=500)
    if feedback.empty:
        st.info("Aucun commentaire reçu.")
    else:
        st.dataframe(feedback, hide_index=True, use_container_width=True)

footer()
