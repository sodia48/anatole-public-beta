from __future__ import annotations

import streamlit as st

from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("Conditions", "📜")
apply_style()
sidebar_context()

page_header(
    "Conditions d’utilisation de la bêta",
    "Règles essentielles applicables aux testeurs publics d’Anatole.",
    "📜",
)

st.markdown(
    """
    ## 1. Nature du service

    Anatole est une version bêta expérimentale destinée à l’information,
    à l’éducation et à l’évaluation du produit.

    ## 2. Aucun conseil financier

    Anatole ne fournit pas de conseil financier, fiscal ou juridique
    personnalisé. Les signaux, résumés, projections et analyses automatiques
    ne constituent pas une recommandation d’achat ou de vente.

    ## 3. Qualité des données

    Les cours et données peuvent être différés, incomplets, indisponibles ou
    erronés. Toute décision doit être vérifiée auprès de sources autorisées.

    ## 4. Utilisation acceptable

    Il est interdit de tenter de contourner les limites, d’automatiser des
    volumes excessifs de requêtes, d’extraire massivement les données, de tester
    les failles sans autorisation ou de perturber le service.

    ## 5. Données de test

    Les portefeuilles saisis doivent être considérés comme des portefeuilles
    de démonstration. N’ajoutez aucune information confidentielle.

    ## 6. Disponibilité

    Le service peut être interrompu, modifié ou réinitialisé sans préavis
    pendant la période de bêta.

    ## 7. Responsabilité

    L’utilisation se fait à vos risques. Anatole n’assume aucune responsabilité
    pour une perte liée à l’utilisation des données ou analyses présentées.

    ## 8. Retours

    Les commentaires transmis peuvent être utilisés pour améliorer le produit,
    sans obligation de mettre en œuvre les suggestions.
    """
)

footer()
