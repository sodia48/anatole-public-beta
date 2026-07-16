from __future__ import annotations

import pandas as pd
import streamlit as st

from core.device import mobile_is_lite
from core.data import fetch_market_snapshot, load_constituents
from core.database import add_watchlist, get_watchlist, remove_watchlist
from core.live_quote import render_live_quote_panel, remember_live_selection
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context, render_mobile_watchlist_card
from core.utils import normalise_symbol



def _watch_value(value, money: bool = False, percent: bool = False) -> str:
    try:
        number = float(value)
    except Exception:
        return "N/D"
    if pd.isna(number):
        return "N/D"
    if money:
        return f"${number:,.2f}"
    if percent:
        return f"{number:+.2f}%"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K"
    return f"{number:,.0f}"


configure_page("Watchlist", "⭐")
apply_style()
profile = sidebar_context()
page_header(
    "Watchlist",
    "Suivez vos titres favoris, leurs signaux clés et les mouvements importants du marché.",
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
table["Secteur"] = table["Secteur"].fillna("Hors univers actif")

if mobile_is_lite():
    st.caption("Vue mobile : cartes lisibles et ouverture rapide vers la fiche Focus.")
    for _, row in table.sort_values("Variation", ascending=False, na_position="last").iterrows():
        render_mobile_watchlist_card(
            ticker=str(row.get("Ticker", row.get("YahooTicker", "N/D"))),
            name=str(row.get("Nom", "N/D")),
            sector=str(row.get("Secteur", "N/D")),
            price=_watch_value(row.get("Prix"), money=True),
            change=_watch_value(row.get("Variation"), percent=True),
            volume=_watch_value(row.get("Volume")),
        )
        mobile_actions = st.columns(2)
        with mobile_actions[0]:
            if st.button(
                "Voir live",
                key=f"live_watch_mobile_{row.get('YahooTicker')}",
                width="stretch",
            ):
                payload = {
                    "ticker": str(row.get("Ticker", row.get("YahooTicker", "N/D"))),
                    "yahoo": str(row.get("YahooTicker", "")),
                    "name": str(row.get("Nom", "")),
                    "sector": str(row.get("Secteur", "")),
                }
                remember_live_selection(payload)
                st.session_state["watchlist_live_ticker"] = payload["yahoo"]
                st.rerun()
        with mobile_actions[1]:
            if st.button(
                "Ouvrir Focus",
                key=f"open_watch_mobile_{row.get('YahooTicker')}",
                width="stretch",
            ):
                st.session_state.selected_ticker = str(row.get("YahooTicker"))
                st.switch_page("screens/14_Focus.py")
else:
    watch_display = table[["Ticker", "Nom", "Secteur", "Prix", "Variation", "PlusHaut", "PlusBas", "Volume", "SourceCours"]].copy()
    watch_event = None
    watch_config = {
        "Prix": st.column_config.NumberColumn(format="$%.2f"),
        "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
        "PlusHaut": st.column_config.NumberColumn(format="$%.2f"),
        "PlusBas": st.column_config.NumberColumn(format="$%.2f"),
        "Volume": st.column_config.NumberColumn(format="compact"),
    }
    try:
        watch_event = st.dataframe(
            watch_display,
            hide_index=True,
            width="stretch",
            column_config=watch_config,
            on_select="rerun",
            selection_mode="single-row",
            key="watchlist_live_selectable_table",
        )
    except TypeError:
        st.dataframe(
            watch_display,
            hide_index=True,
            width="stretch",
            column_config=watch_config,
        )

    try:
        selected_rows = list(watch_event.selection.rows) if watch_event is not None else []
    except Exception:
        selected_rows = []
    if selected_rows:
        picked = table.iloc[int(selected_rows[0])]
        payload = {
            "ticker": str(picked.get("Ticker", picked.get("YahooTicker", ""))),
            "yahoo": str(picked.get("YahooTicker", "")),
            "name": str(picked.get("Nom", "")),
            "sector": str(picked.get("Secteur", "")),
        }
        remember_live_selection(payload)
        st.session_state["watchlist_live_ticker"] = payload["yahoo"]

live_ticker = str(st.session_state.get("watchlist_live_ticker") or "").strip()
if live_ticker:
    match = table[table["YahooTicker"].astype(str) == live_ticker].head(1)
    if not match.empty:
        picked = match.iloc[0]
        render_live_quote_panel(
            live_ticker,
            symbol=str(picked.get("Ticker", live_ticker)),
            name=str(picked.get("Nom", "")),
            sector=str(picked.get("Secteur", "")),
            key_prefix="watchlist_live_quote",
            compact=True,
            refresh_seconds=10,
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
