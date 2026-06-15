from __future__ import annotations

import platform
import sys

import pandas as pd
import streamlit as st

from core.config import EXPECTED_CONSTITUENTS
from core.data import load_constituents
from core.database import database_backend, database_location, get_alerts, get_positions, get_watchlist
from core.runtime import load_market_bundle
from core.ui import apply_style, configure_page, dependency_version, footer, page_header, sidebar_context
from core.utils import get_secret

configure_page("Diagnostics", "🛠️")
apply_style()
profile = sidebar_context()
page_header(
    "Diagnostics et qualité des données",
    "Vérifie la composition, la couverture des cotations, les dépendances et la configuration locale.",
    "🛠️",
)

constituents, diagnostics, snapshot, features = load_market_bundle()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Constituants attendus", EXPECTED_CONSTITUENTS)
m2.metric("Constituants récupérés", len(constituents))
m3.metric("Cotations disponibles", int(snapshot["Prix"].notna().sum()))
m4.metric("Historiques techniques", int(features["CloseTech"].notna().sum()))

st.subheader("Audit de composition")
st.json(diagnostics)
st.dataframe(constituents, hide_index=True, width="stretch")

missing_quotes = snapshot[snapshot["Prix"].isna()][["Ticker", "Nom", "YahooTicker"]]
if not missing_quotes.empty:
    st.warning("Cotations manquantes")
    st.dataframe(missing_quotes, hide_index=True, width="stretch")

st.subheader("Environnement")
environment = pd.DataFrame(
    [
        ("Python", sys.version.split()[0]),
        ("Système", platform.platform()),
        ("Streamlit", dependency_version("streamlit")),
        ("yfinance", dependency_version("yfinance")),
        ("pandas", dependency_version("pandas")),
        ("plotly", dependency_version("plotly")),
        ("streamlit-plotly-events2", dependency_version("streamlit-plotly-events2")),
        ("Base de données", database_backend()),
        ("Emplacement", database_location()),
    ],
    columns=["Élément", "Valeur"],
)
st.dataframe(environment, hide_index=True, width="stretch")

st.subheader("Données persistantes du profil")
p1, p2, p3 = st.columns(3)
p1.metric("Watchlist", len(get_watchlist(profile)))
p2.metric("Positions", len(get_positions(profile)))
p3.metric("Alertes", len(get_alerts(profile)))

st.subheader("Intégrations")
integrations = pd.DataFrame(
    [
        ("Twelve Data", bool(get_secret("TWELVE_DATA_API_KEY"))),
        ("Telegram", bool(get_secret("TELEGRAM_BOT_TOKEN") and get_secret("TELEGRAM_CHAT_ID"))),
        ("Courriel SMTP", bool(get_secret("SMTP_HOST") and get_secret("SMTP_USERNAME") and get_secret("SMTP_PASSWORD") and get_secret("ALERT_EMAIL_TO"))),
    ],
    columns=["Intégration", "Configurée"],
)
st.dataframe(integrations, hide_index=True, width="stretch")

if st.button("♻️ Effacer les caches Streamlit", type="primary"):
    st.cache_data.clear()
    st.success("Caches effacés.")
    st.rerun()

footer()
