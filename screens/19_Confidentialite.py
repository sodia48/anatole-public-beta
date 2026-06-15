from __future__ import annotations

import streamlit as st

from core.database import delete_profile_data
from core.public_beta import current_context
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("Confidentialité", "🔒")
apply_style()
profile = sidebar_context()
context = current_context()

page_header(
    "Avis de confidentialité",
    "Ce que la bêta Anatole collecte, conserve et transmet.",
    "🔒",
)

st.markdown(
    """
    ## Données traitées

    Anatole peut conserver, selon les fonctions utilisées :

    - un identifiant technique de profil ;
    - votre adresse courriel et votre nom si vous utilisez la connexion OIDC ;
    - vos watchlists, positions de démonstration, préférences et alertes ;
    - vos commentaires transmis dans le formulaire de bêta ;
    - des journaux techniques nécessaires au diagnostic.

    ## Données à ne pas saisir

    Ne saisissez jamais dans Anatole :

    - vos mots de passe ;
    - des numéros de comptes bancaires ou de courtage ;
    - des numéros de carte ;
    - des documents d’identité ;
    - des clés API dans les champs de l’interface.

    ## Services externes

    Les fonctions peuvent interroger Yahoo Finance, BlackRock, Statistique Canada,
    la Banque du Canada, le BLS, le BEA, la Réserve fédérale et certains services externes facultatifs. Les politiques de ces services peuvent alors s’appliquer.

    ## Conservation et suppression

    En mode invité, les données peuvent être temporaires. En mode connecté,
    elles sont rattachées à un identifiant pseudonymisé. Vous pouvez demander
    leur suppression ci-dessous.

    ## Sécurité

    Anatole est une bêta. Des mesures raisonnables sont appliquées, mais aucun
    système ne peut garantir une sécurité absolue.
    """
)

st.divider()
st.subheader("Supprimer mes données Anatole")
st.warning(
    "Cette action supprime la watchlist, les positions, alertes, notifications, "
    "préférences, espaces de travail et commentaires associés à ce profil."
)

confirmation = st.text_input(
    "Tape SUPPRIMER pour confirmer",
    key="delete_profile_confirmation",
)

if st.button(
    "Supprimer définitivement mes données",
    type="primary",
    disabled=confirmation != "SUPPRIMER",
):
    delete_profile_data(profile)
    for key in list(st.session_state):
        if key not in {"_page_configured"}:
            del st.session_state[key]
    st.success("Les données du profil ont été supprimées.")
    st.stop()

footer()
