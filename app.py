from __future__ import annotations

import streamlit as st

from core.logging_config import configure_logging
from core.public_beta import bootstrap_public_beta
from core.ui import configure_page


configure_page("Anatole", "📈")
logger = configure_logging()
beta = bootstrap_public_beta()
st.session_state["_navigation_entrypoint"] = True

pages = {
    "MARCHÉS": [
        st.Page(
            "screens/0_Accueil.py",
            title="Cockpit",
            icon="🏠",
            default=True,
            url_path="cockpit",
        ),
        st.Page(
            "screens/1_Screener.py",
            title="Screener",
            icon="🔎",
            url_path="screener",
        ),
        st.Page(
            "screens/5_Actualites.py",
            title="Actualités",
            icon="📰",
            url_path="actualites",
        ),
        st.Page(
            "screens/6_Calendrier.py",
            title="Calendrier",
            icon="🗓️",
            url_path="calendrier",
        ),
        st.Page(
            "screens/24_IPO.py",
            title="IPO à venir",
            icon="🚀",
            url_path="ipo",
        ),
        st.Page(
            "screens/25_Insiders.py",
            title="Transactions d’initiés",
            icon="🕵️",
            url_path="insiders",
        ),
        st.Page(
            "screens/15_Market_Drivers.py",
            title="Moteurs du marché",
            icon="🧭",
            url_path="moteurs-marche",
        ),
        st.Page(
            "screens/23_Psychologie.py",
            title="Psychologie",
            icon="🧠",
            url_path="psychologie",
        ),
    ],
    "ANALYSE": [
        st.Page(
            "screens/14_Focus.py",
            title="Mode Focus",
            icon="🎯",
            url_path="focus",
        ),
        st.Page(
            "screens/2_Comparateur.py",
            title="Comparateur",
            icon="⚖️",
            url_path="comparateur",
        ),
        st.Page(
            "screens/7_Backtesting.py",
            title="Backtesting",
            icon="🧪",
            url_path="backtesting",
        ),
        st.Page(
            "screens/8_Correlations.py",
            title="Corrélations",
            icon="🧩",
            url_path="correlations",
        ),
    ],
    "MON ESPACE": [
        st.Page(
            "screens/3_Portefeuille.py",
            title="Portefeuille",
            icon="💼",
            url_path="portefeuille",
        ),
        st.Page(
            "screens/9_Watchlist.py",
            title="Watchlist",
            icon="⭐",
            url_path="watchlist",
        ),
        st.Page(
            "screens/4_Alertes.py",
            title="Alertes",
            icon="🔔",
            url_path="alertes",
        ),
        st.Page(
            "screens/11_Workspaces.py",
            title="Espaces de travail",
            icon="🧱",
            url_path="espaces",
        ),
        st.Page(
            "screens/12_Reports.py",
            title="Rapports",
            icon="📄",
            url_path="rapports",
        ),
        st.Page(
            "screens/17_Preferences.py",
            title="Préférences",
            icon="⚙️",
            url_path="preferences",
        ),
    ],
    "INTELLIGENCE": [
        st.Page(
            "screens/13_Assistant.py",
            title="Assistant contextuel",
            icon="✨",
            url_path="assistant",
        ),
        st.Page(
            "screens/16_Notifications.py",
            title="Centre de notifications",
            icon="🔔",
            url_path="notifications",
        ),
    ],
    "BÊTA PUBLIQUE": [
        st.Page(
            "screens/18_Feedback.py",
            title="Donner mon avis",
            icon="💬",
            url_path="feedback",
        ),
        st.Page(
            "screens/19_Confidentialite.py",
            title="Confidentialité",
            icon="🔒",
            url_path="confidentialite",
        ),
        st.Page(
            "screens/20_Conditions.py",
            title="Conditions",
            icon="📜",
            url_path="conditions",
        ),
        st.Page(
            "screens/21_Beta_Status.py",
            title="État de la bêta",
            icon="🧪",
            url_path="etat-beta",
        ),
    ],
}

if beta.is_admin:
    pages["ADMINISTRATION"] = [
        st.Page(
            "screens/10_Diagnostics.py",
            title="Diagnostics",
            icon="🛠️",
            url_path="diagnostics",
        )
    ]

logger.info(
    "session_started profile=%s authenticated=%s admin=%s beta=%s",
    beta.profile,
    beta.authenticated,
    beta.is_admin,
    beta.public_beta,
)

navigation = st.navigation(pages, position="sidebar", expanded=True)
navigation.run()
