from __future__ import annotations

import pandas as pd
import streamlit as st

from core.data import fetch_market_snapshot, load_constituents
from core.database import add_watchlist, get_watchlist, remove_watchlist
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import normalise_symbol

configure_page("Watchlist", "⭐")
apply_style()
profile = sidebar_context()
page_header(
    "Watchlist persistante",
    "Gère une liste enregistrée dans SQLite, retrouvée après fermeture du navigateur.",
    "⭐",
)

constituents, diagnostics = load_constituents()
lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))

with st.form("add_watchlist"):
    c1, c2 = st.columns([3, 1])
    with c1:
        symbol = st.text_input("Ajouter un symbole", placeholder="RY.TO, SHOP.TO, AAPL, TECK.B")
    with c2:
        st.write("")
        submitted = st.form_submit_button("Ajouter", width="stretch")
    if submitted:
        normalized = normalise_symbol(symbol, constituents)
        if normalized:
            add_watchlist(profile, normalized)
            st.success(f"{normalized} ajouté.")
            st.rerun()
        else:
            st.error("Symbole invalide.")

watchlist = get_watchlist(profile)
if not watchlist:
    st.info("La watchlist est vide.")
    footer()
    st.stop()

quotes = fetch_market_snapshot(tuple(watchlist))
names = constituents[["YahooTicker", "Ticker", "Nom", "Secteur"]]
table = pd.DataFrame({"YahooTicker": watchlist}).merge(names, on="YahooTicker", how="left").merge(quotes, on="YahooTicker", how="left")
table["Ticker"] = table["Ticker"].fillna(table["YahooTicker"])
table["Nom"] = table["Nom"].fillna(table["YahooTicker"])
table["Secteur"] = table["Secteur"].fillna("Hors TSX 60")

st.dataframe(
    table[["Ticker", "Nom", "Secteur", "Prix", "Variation", "PlusHaut", "PlusBas", "Volume", "SourceCours"]],
    hide_index=True,
    width="stretch",
    column_config={
        "Prix": st.column_config.NumberColumn(format="$%.2f"),
        "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
        "PlusHaut": st.column_config.NumberColumn(format="$%.2f"),
        "PlusBas": st.column_config.NumberColumn(format="$%.2f"),
        "Volume": st.column_config.NumberColumn(format="compact"),
    },
)

remove = st.selectbox("Retirer un titre", watchlist)
if st.button("Retirer de la watchlist"):
    remove_watchlist(profile, remove)
    st.rerun()

st.download_button(
    "Télécharger la watchlist",
    table.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"watchlist_{profile}.csv",
    mime="text/csv",
)

footer()
