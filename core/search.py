from __future__ import annotations

import html
import re

import streamlit as st

from core.data import load_constituents
from core.database import add_watchlist, set_preference

RECENT_SEARCHES_KEY = "_anatole_recent_searches"


PAGE_COMMANDS = [
    ("Vue d'ensemble", "screens/0_Accueil.py", "marché accueil cockpit dashboard"),
    ("Screener", "screens/1_Screener.py", "filtre actions rsi dividende"),
    ("Actualités", "screens/5_Actualites.py", "news sentiment manchettes"),
    ("Psychologie", "screens/23_Psychologie.py", "fear greed sentiment psychologie marché humeur risque confiance anxiété breadth rsi momentum"),
    ("Calendrier", "screens/6_Calendrier.py", "résultats dividendes macro"),
    ("IPO à venir", "screens/24_IPO.py", "ipo introduction bourse nouvel entrant calendrier sociétés bientôt cotées nasdaq nyse tsx"),
    ("Transactions d’initiés", "screens/25_Insiders.py", "insider initié insiders dirigeant administrateur transactions achats ventes SEDI TMX"),
    ("Mode Focus", "screens/14_Focus.py", "graphique action finances"),
    ("Comparateur", "screens/2_Comparateur.py", "comparer titres performance"),
    ("Backtesting", "screens/7_Backtesting.py", "stratégie historique"),
    ("Corrélations", "screens/8_Correlations.py", "diversification matrice"),
    ("Portefeuille", "screens/3_Portefeuille.py", "positions risque rendement"),
    ("Watchlist", "screens/9_Watchlist.py", "favoris suivi"),
    ("Alertes", "screens/4_Alertes.py", "prix rsi notifications"),
    ("Assistant", "screens/13_Assistant.py", "question ia analyse"),
    ("Rapports", "screens/12_Reports.py", "pdf excel résumé"),
    ("Préférences", "screens/17_Preferences.py", "thème affichage réglages"),
]


SHORTCUT_JS = """
export default function(component) {
  const handler = (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      const inputs = [...document.querySelectorAll('input')];
      const target = inputs.find(x => (x.placeholder || '').includes('Rechercher'));
      if (target) { target.focus(); target.scrollIntoView({behavior:'smooth', block:'center'}); }
    }
  };
  document.addEventListener('keydown', handler);
  return () => document.removeEventListener('keydown', handler);
}
"""


def install_command_shortcut() -> None:
    try:
        shortcut_component = st.components.v2.component("skyline_ctrl_k_minimal", js=SHORTCUT_JS)
        shortcut_component(key="skyline_ctrl_k_minimal_instance", width="content", height=0)
    except Exception:
        # La recherche reste pleinement utilisable même si le composant V2 n'est pas disponible.
        pass


def _register_recent_search(query: str) -> None:
    clean = str(query or "").strip()
    if not clean:
        return
    history = list(st.session_state.get(RECENT_SEARCHES_KEY, []))
    history = [item for item in history if str(item).strip().lower() != clean.lower()]
    history.insert(0, clean)
    st.session_state[RECENT_SEARCHES_KEY] = history[:8]


def render_recent_searches(location: str = "page") -> None:
    history = list(st.session_state.get(RECENT_SEARCHES_KEY, []))
    if not history:
        return
    host = st.sidebar if location == "sidebar" else st
    host.caption("Recherches récentes")
    max_items = 5 if location == "sidebar" else 8
    for index, item in enumerate(history[:max_items]):
        label = item if len(item) <= 28 else item[:25] + "..."
        if host.button(label, key=f"recent_search_{location}_{index}", width="stretch"):
            st.session_state[f"universal_search_{location}"] = item
            st.rerun()


def _normalize_requested_ticker(raw: str, constituents) -> str:
    clean = raw.strip().upper()
    if not clean:
        return ""
    ticker_map = dict(zip(constituents["Ticker"], constituents["YahooTicker"]))
    if clean in ticker_map:
        return ticker_map[clean]
    if clean.endswith(".TO"):
        return clean
    return clean


def render_universal_search(
    location: str = "sidebar",
    profile: str | None = None,
    label: str = "Recherche universelle",
    placeholder: str = "Rechercher un titre, une page ou une commande…",
    navigate_on_select: bool = True,
    show_inline_results: bool = True,
) -> None:
    install_command_shortcut()
    host = st.sidebar if location == "sidebar" else st
    query = host.text_input(
        label,
        placeholder=placeholder,
        key=f"universal_search_{location}",
        label_visibility="collapsed",
    ).strip()

    if not query:
        render_recent_searches(location)
        return

    if len(query) >= 2:
        _register_recent_search(query)

    constituents, _ = load_constituents()
    lowered = query.lower()

    with host.container(border=(location == "sidebar")):
        # Commandes rapides sobres.
        if lowered in {"mode sombre", "thème sombre", "theme sombre"}:
            if st.button("Activer le mode sombre", key=f"search_dark_{location}", width="stretch"):
                st.session_state.theme_toggle = True
                if profile:
                    set_preference(profile, "theme", "dark")
                st.rerun()
            return

        if lowered in {"mode clair", "thème clair", "theme clair"}:
            if st.button("Activer le mode clair", key=f"search_light_{location}", width="stretch"):
                st.session_state.theme_toggle = False
                if profile:
                    set_preference(profile, "theme", "light")
                st.rerun()
            return

        watch_match = re.match(r"(?:ajouter|add)\s+([A-Za-z0-9.\-]+)\s+(?:à\s+la\s+)?watchlist", query, re.I)
        if watch_match and profile:
            symbol = _normalize_requested_ticker(watch_match.group(1), constituents)
            if st.button(f"Ajouter {symbol} à la watchlist", key=f"search_add_watch_{location}", width="stretch"):
                add_watchlist(profile, symbol)
                st.success(f"{symbol} ajouté.")
            return

        compare_match = re.match(r"comparer\s+([A-Za-z0-9.\-]+)\s+(?:et|avec)\s+([A-Za-z0-9.\-]+)", query, re.I)
        if compare_match:
            first = _normalize_requested_ticker(compare_match.group(1), constituents)
            second = _normalize_requested_ticker(compare_match.group(2), constituents)
            if st.button(f"Comparer {first} et {second}", key=f"search_compare_{location}", width="stretch"):
                st.session_state.comparison_tickers = [first, second]
                st.switch_page("screens/2_Comparateur.py")
            return

        pages = [item for item in PAGE_COMMANDS if lowered in (item[0] + " " + item[2]).lower()]
        mask = (
            constituents["Ticker"].astype(str).str.lower().str.contains(lowered, regex=False)
            | constituents["Nom"].astype(str).str.lower().str.contains(lowered, regex=False)
            | constituents["Secteur"].astype(str).str.lower().str.contains(lowered, regex=False)
        )
        stocks = constituents.loc[mask].head(8).copy()

        if not stocks.empty:
            st.caption("Titres")
            if show_inline_results:
                display = stocks[[col for col in ["Ticker", "Nom", "Secteur"] if col in stocks.columns]].copy()
                display = display.rename(columns={"Ticker": "Symbole"})
                st.dataframe(display, hide_index=True, width="stretch")

            if navigate_on_select:
                for _, row in stocks.iterrows():
                    if st.button(
                        f"{row['Ticker']} · {row['Nom']}",
                        key=f"search_stock_{location}_{row['YahooTicker']}",
                        width="stretch",
                    ):
                        st.session_state.selected_ticker = row["YahooTicker"]
                        st.switch_page("screens/14_Focus.py")
            else:
                first = stocks.iloc[0]
                st.caption(f"Meilleure correspondance : {first['Ticker']} · {first['Nom']}")
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button(
                        f"Ouvrir {first['Ticker']} dans Focus",
                        key=f"search_focus_{location}_{first['YahooTicker']}",
                        width="stretch",
                    ):
                        st.session_state.selected_ticker = first["YahooTicker"]
                        st.switch_page("screens/14_Focus.py")
                with c2:
                    if profile and st.button(
                        f"Ajouter {first['Ticker']} à la watchlist",
                        key=f"search_watch_{location}_{first['YahooTicker']}",
                        width="stretch",
                    ):
                        add_watchlist(profile, first["YahooTicker"])
                        st.success(f"{first['Ticker']} ajouté à la watchlist.")

        if pages:
            st.caption("Pages")
            for title, path, _ in pages[:5]:
                st.page_link(path, label=title, width="stretch")

        if stocks.empty and not pages:
            st.caption(f"Aucun résultat pour « {html.escape(query)} ».")
