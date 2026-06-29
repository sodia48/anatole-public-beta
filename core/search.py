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
    ("Calendrier", "screens/6_Calendrier.py", "résultats dividendes macro"),
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
    for index, item in enumerate(history[:5]):
        label = item if len(item) <= 22 else item[:19] + "..."
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


def render_universal_search(location: str = "sidebar", profile: str | None = None) -> None:
    install_command_shortcut()
    host = st.sidebar if location == "sidebar" else st
    query = host.text_input(
        "Recherche universelle",
        placeholder="Rechercher un titre, une page ou une commande…",
        key=f"universal_search_{location}",
        label_visibility="collapsed",
    ).strip()

    if not query:
        render_recent_searches(location)
        return

    _register_recent_search(query)
    constituents, _ = load_constituents()
    lowered = query.lower()

    with host.container(border=True):
        # Commandes rapides sobres.
        if lowered in {"mode sombre", "thème sombre", "theme sombre"}:
            if host.button("Activer le mode sombre", width="stretch"):
                st.session_state.theme_toggle = True
                if profile:
                    set_preference(profile, "theme", "dark")
                st.rerun()
            return

        if lowered in {"mode clair", "thème clair", "theme clair"}:
            if host.button("Activer le mode clair", width="stretch"):
                st.session_state.theme_toggle = False
                if profile:
                    set_preference(profile, "theme", "light")
                st.rerun()
            return

        watch_match = re.match(r"(?:ajouter|add)\s+([A-Za-z0-9.\-]+)\s+(?:à\s+la\s+)?watchlist", query, re.I)
        if watch_match and profile:
            symbol = _normalize_requested_ticker(watch_match.group(1), constituents)
            if host.button(f"Ajouter {symbol} à la watchlist", width="stretch"):
                add_watchlist(profile, symbol)
                host.success(f"{symbol} ajouté.")
            return

        compare_match = re.match(r"comparer\s+([A-Za-z0-9.\-]+)\s+(?:et|avec)\s+([A-Za-z0-9.\-]+)", query, re.I)
        if compare_match:
            first = _normalize_requested_ticker(compare_match.group(1), constituents)
            second = _normalize_requested_ticker(compare_match.group(2), constituents)
            if host.button(f"Comparer {first} et {second}", width="stretch"):
                st.session_state.comparison_tickers = [first, second]
                st.switch_page("screens/2_Comparateur.py")
            return

        pages = [item for item in PAGE_COMMANDS if lowered in (item[0] + " " + item[2]).lower()]
        mask = (
            constituents["Ticker"].str.lower().str.contains(lowered, regex=False)
            | constituents["Nom"].str.lower().str.contains(lowered, regex=False)
            | constituents["Secteur"].str.lower().str.contains(lowered, regex=False)
        )
        stocks = constituents.loc[mask].head(6)

        if not stocks.empty:
            host.caption("Titres")
            for _, row in stocks.iterrows():
                if host.button(
                    f"{row['Ticker']} · {row['Nom']}",
                    key=f"search_stock_{location}_{row['YahooTicker']}",
                    width="stretch",
                ):
                    st.session_state.selected_ticker = row["YahooTicker"]
                    st.switch_page("screens/14_Focus.py")

        if pages:
            host.caption("Pages")
            for title, path, _ in pages[:5]:
                host.page_link(path, label=title, width="stretch")

        if stocks.empty and not pages:
            host.caption(f"Aucun résultat pour « {html.escape(query)} ».")
