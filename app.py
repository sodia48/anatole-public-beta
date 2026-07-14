from __future__ import annotations

import logging
import traceback

import streamlit as st

from core.logging_config import configure_logging
from core.public_beta import bootstrap_public_beta
from core.ui import configure_page


configure_page("Anatole", "📈")
logger = configure_logging()
beta = bootstrap_public_beta()
st.session_state["_navigation_entrypoint"] = True


MOBILE_NAV_DEFAULTS = {
    "accueil": "cockpit",
    "home": "cockpit",
    "cockpit": "cockpit",
    "aujourdhui": "aujourd-hui",
    "today": "aujourd-hui",
    "brief": "aujourd-hui",
    "daily": "aujourd-hui",
    "recherche": "cockpit",
    "search": "cockpit",
    "screener": "screener",
    "focus": "focus",
    "liste": "watchlist",
    "watchlist": "watchlist",
    "terminal": "terminal-pro",
    "pro": "terminal-pro",
}


def _requested_mobile_default() -> str | None:
    """Retourne la page demandée par la navigation mobile sans route brute."""
    try:
        raw_value = st.query_params.get("nav")
    except Exception:
        return None
    if isinstance(raw_value, list):
        raw_value = raw_value[0] if raw_value else ""
    key = str(raw_value or "").strip().lower()
    return MOBILE_NAV_DEFAULTS.get(key)


REQUESTED_MOBILE_DEFAULT = _requested_mobile_default()


def _make_page(path: str, *, title: str, icon: str, url_path: str, default: bool = False):
    """Crée une page Streamlit avec un défaut dynamique pour la navigation mobile."""
    is_default = (url_path == REQUESTED_MOBILE_DEFAULT) or (REQUESTED_MOBILE_DEFAULT is None and default)
    return st.Page(path, title=title, icon=icon, url_path=url_path, default=is_default)

pages = {
    "MARCHÉS": [
        _make_page(
            "screens/0_Accueil.py",
            title="Cockpit",
            icon="🏠",
            default=True,
            url_path="cockpit",
        ),
        _make_page(
            "screens/28_AujourdHui.py",
            title="Aujourd’hui",
            icon="⚡",
            url_path="aujourd-hui",
        ),
        _make_page(
            "screens/1_Screener.py",
            title="Screener",
            icon="🔎",
            url_path="screener",
        ),
        _make_page(
            "screens/5_Actualites.py",
            title="Actualités",
            icon="📰",
            url_path="actualites",
        ),
        _make_page(
            "screens/6_Calendrier.py",
            title="Calendrier",
            icon="🗓️",
            url_path="calendrier",
        ),
        _make_page(
            "screens/26_ETF.py",
            title="ETF sectoriels",
            icon="🧺",
            url_path="etf-sectoriels",
        ),
        _make_page(
            "screens/24_IPO.py",
            title="IPO à venir",
            icon="🚀",
            url_path="ipo",
        ),
        _make_page(
            "screens/25_Insiders.py",
            title="Transactions d’initiés",
            icon="🕵️",
            url_path="insiders",
        ),
        _make_page(
            "screens/15_Market_Drivers.py",
            title="Moteurs du marché",
            icon="🧭",
            url_path="moteurs-marche",
        ),
        _make_page(
            "screens/23_Psychologie.py",
            title="Psychologie",
            icon="🧠",
            url_path="psychologie",
        ),
    ],
    "ANALYSE": [
        _make_page(
            "screens/14_Focus.py",
            title="Mode Focus",
            icon="🎯",
            url_path="focus",
        ),
        _make_page(
            "screens/2_Comparateur.py",
            title="Comparateur",
            icon="⚖️",
            url_path="comparateur",
        ),
        _make_page(
            "screens/7_Backtesting.py",
            title="Backtesting",
            icon="🧪",
            url_path="backtesting",
        ),
        _make_page(
            "screens/8_Correlations.py",
            title="Corrélations",
            icon="🧩",
            url_path="correlations",
        ),
    ],
    "MON ESPACE": [
        _make_page(
            "screens/3_Portefeuille.py",
            title="Portefeuille",
            icon="💼",
            url_path="portefeuille",
        ),
        _make_page(
            "screens/9_Watchlist.py",
            title="Watchlist",
            icon="⭐",
            url_path="watchlist",
        ),
        _make_page(
            "screens/4_Alertes.py",
            title="Alertes",
            icon="🔔",
            url_path="alertes",
        ),
        _make_page(
            "screens/11_Workspaces.py",
            title="Espaces de travail",
            icon="🧱",
            url_path="espaces",
        ),
        _make_page(
            "screens/12_Reports.py",
            title="Rapports",
            icon="📄",
            url_path="rapports",
        ),
        _make_page(
            "screens/17_Preferences.py",
            title="Préférences",
            icon="⚙️",
            url_path="preferences",
        ),
    ],
    "INTELLIGENCE": [
        _make_page(
            "screens/27_Terminal_Pro.py",
            title="Terminal Pro",
            icon="💎",
            url_path="terminal-pro",
        ),
        _make_page(
            "screens/13_Assistant.py",
            title="Assistant contextuel",
            icon="✨",
            url_path="assistant",
        ),
        _make_page(
            "screens/16_Notifications.py",
            title="Centre de notifications",
            icon="🔔",
            url_path="notifications",
        ),
    ],
    "BÊTA PUBLIQUE": [
        _make_page(
            "screens/18_Feedback.py",
            title="Donner mon avis",
            icon="💬",
            url_path="feedback",
        ),
        _make_page(
            "screens/19_Confidentialite.py",
            title="Confidentialité",
            icon="🔒",
            url_path="confidentialite",
        ),
        _make_page(
            "screens/20_Conditions.py",
            title="Conditions",
            icon="📜",
            url_path="conditions",
        ),
        _make_page(
            "screens/21_Beta_Status.py",
            title="État de la bêta",
            icon="🧪",
            url_path="etat-beta",
        ),
    ],
}

if beta.is_admin:
    pages["ADMINISTRATION"] = [
        _make_page(
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

try:
    navigation.run()
except Exception as exc:
    logging.exception("anatole_page_runtime_error")
    st.error("Cette section est temporairement indisponible. Anatole reste accessible : retournez à l’accueil ou ouvrez une autre section depuis le menu.")
    st.markdown("### Revenir au cockpit")
    st.page_link("screens/0_Accueil.py", label="Ouvrir l’accueil", icon="🏠")
    if beta.is_admin:
        with st.expander("Détail technique administrateur", expanded=False):
            st.code("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
