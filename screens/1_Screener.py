from __future__ import annotations

import pandas as pd
import streamlit as st

from core.analytics import apply_screener_preset, technical_signal
from core.data import fetch_fundamentals
from core.data_quality import render_data_quality_strip
from core.device import mobile_is_lite, mobile_page_limit
from core.performance import load_timer, perf_caption
from core.live_quote import render_live_quote_panel, remember_live_selection
from core.runtime import load_market_bundle
from core.universe import current_universe, current_universe_key
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context



def _clean_symbol(value: object) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text.replace("-", ".")


def _incoming_screener_symbol() -> str:
    candidates = [
        st.session_state.get("screener_symbol_query"),
        st.session_state.get("anatole_bridge_ticker"),
        st.session_state.get("selected_ticker"),
    ]
    try:
        raw = st.query_params.get("ticker")
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        candidates.append(raw)
    except Exception:
        pass
    for candidate in candidates:
        cleaned = _clean_symbol(candidate)
        if cleaned:
            return cleaned
    return ""


def _sync_screener_search_from_bridge() -> None:
    incoming = _incoming_screener_symbol()
    if not incoming:
        return
    marker = st.session_state.get("_last_screener_bridge_symbol")
    if marker != incoming:
        st.session_state["screener_symbol_search"] = incoming
        st.session_state["_last_screener_bridge_symbol"] = incoming


def _route_symbol(symbol: str, yahoo: str, page: str) -> None:
    symbol = _clean_symbol(symbol)
    yahoo = str(yahoo or symbol).strip()
    if symbol:
        st.session_state["anatole_bridge_ticker"] = symbol
        st.session_state["screener_symbol_query"] = symbol
        st.session_state["selected_ticker"] = yahoo
        st.session_state["focus_ticker"] = yahoo
        st.session_state["insider_symbol_query"] = symbol
        st.session_state["alert_prefill_ticker"] = yahoo
    targets = {
        "Focus": "screens/14_Focus.py",
        "Insiders": "screens/25_Insiders.py",
        "Alertes": "screens/4_Alertes.py",
        "Watchlist": "screens/9_Watchlist.py",
    }
    try:
        st.switch_page(targets[page])
    except Exception:
        st.info("Le titre est mémorisé. Ouvre la section souhaitée depuis la navigation pour continuer.")


configure_page("Screener", "🔎")
apply_style()
profile = sidebar_context()
page_header(
    f"Screener {current_universe().short_label}",
    "Filtre les titres selon le momentum, la tendance, le RSI, le volume et, en option, les fondamentaux.",
    "🔎",
)

_sync_screener_search_from_bridge()

with load_timer("screener"):
    constituents, diagnostics, snapshot, features = load_market_bundle()
features = features.copy()
REQUIRED_TECHNICAL_COLUMNS = [
    "Variation",
    "RSI14",
    "VolumeRelatif",
    "Momentum1M",
    "Momentum3M",
    "Volatilite20",
    "DistanceHigh52",
    "AboveSMA50",
    "AboveSMA200",
    "AboveSMA20",
    "MACD",
    "SignalMACD",
]
for column in REQUIRED_TECHNICAL_COLUMNS:
    if column not in features:
        features[column] = pd.NA if column not in {"AboveSMA50", "AboveSMA200", "AboveSMA20"} else False

render_data_quality_strip(snapshot, diagnostics, compact=True)
perf_caption("screener", threshold=2.5)
features["Signal"] = features.apply(technical_signal, axis=1)

features["__TickerClean"] = features["Ticker"].map(_clean_symbol)
features["__YahooClean"] = features.get("YahooTicker", features["Ticker"]).map(_clean_symbol)

bridge_symbol = _incoming_screener_symbol()
if bridge_symbol:
    matched_bridge = features[
        (features["__TickerClean"] == bridge_symbol)
        | (features["__YahooClean"] == bridge_symbol)
    ].head(1)
    if not matched_bridge.empty:
        bridge_row = matched_bridge.iloc[0]
        st.success(
            f"{bridge_row.get('Ticker', bridge_symbol)} ouvert depuis une autre section · "
            f"{bridge_row.get('Nom', '')}"
        )
        bridge_payload = {
            "ticker": str(bridge_row.get("Ticker", bridge_symbol)),
            "yahoo": str(bridge_row.get("YahooTicker", bridge_symbol)),
            "name": str(bridge_row.get("Nom", "")),
            "sector": str(bridge_row.get("Secteur", "")),
        }
        remember_live_selection(bridge_payload)
        render_live_quote_panel(
            bridge_payload["yahoo"],
            symbol=bridge_payload["ticker"],
            name=bridge_payload["name"],
            sector=bridge_payload["sector"],
            key_prefix="screener_bridge_live",
            compact=True,
        )
        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("Mode Focus", key="screener_bridge_focus", width="stretch"):
                _route_symbol(str(bridge_row.get("Ticker", bridge_symbol)), str(bridge_row.get("YahooTicker", bridge_symbol)), "Focus")
        with b2:
            if st.button("Insiders", key="screener_bridge_insiders", width="stretch"):
                _route_symbol(str(bridge_row.get("Ticker", bridge_symbol)), str(bridge_row.get("YahooTicker", bridge_symbol)), "Insiders")
        with b3:
            if st.button("Créer une alerte", key="screener_bridge_alert", width="stretch"):
                _route_symbol(str(bridge_row.get("Ticker", bridge_symbol)), str(bridge_row.get("YahooTicker", bridge_symbol)), "Alertes")
        with b4:
            if st.button("Ajouter à la liste", key="screener_bridge_watchlist", width="stretch"):
                _route_symbol(str(bridge_row.get("Ticker", bridge_symbol)), str(bridge_row.get("YahooTicker", bridge_symbol)), "Watchlist")

search_cols = st.columns([2.2, 1])
with search_cols[0]:
    symbol_search = st.text_input(
        "Rechercher dans le screener",
        key="screener_symbol_search",
        placeholder="RY, TD, Shopify, énergie, banques…",
        help="Recherche par symbole, nom ou secteur. Les actions cliquées dans la carte arrivent automatiquement ici.",
    ).strip()
with search_cols[1]:
    exact_symbol_only = st.toggle(
        "Symbole exact",
        value=bool(bridge_symbol),
        key="screener_exact_symbol_only",
        help="Active un filtre strict sur le symbole quand tu arrives depuis la carte du marché.",
    )

if mobile_is_lite():
    st.info(
        "Mode mobile allégé : garde les fondamentaux désactivés pour préserver la vitesse. "
        "Tu peux toujours filtrer par tendance, variation, RSI et volume."
    )
else:
    st.info(
        "Les critères techniques sont disponibles immédiatement. Les fondamentaux sont mis en cache 24 heures, "
        "mais leur premier chargement peut prendre un peu plus de temps."
    )

controls = st.columns([1.4, 1, 1, 1])
with controls[0]:
    preset = st.selectbox(
        "Filtre prédéfini",
        [
            "Tous",
            "Momentum haussier",
            "Actions survendues",
            "Cassures / volume",
            "Tendance long terme",
            "Dividendes élevés",
            "Valorisation faible",
        ],
    )
with controls[1]:
    load_fundamentals = st.checkbox("Charger les fondamentaux", value=False)
with controls[2]:
    min_change = st.number_input("Variation min. (%)", value=-20.0, step=0.5)
with controls[3]:
    max_change = st.number_input("Variation max. (%)", value=20.0, step=0.5)

if load_fundamentals:
    with st.spinner("Chargement des fondamentaux..."):
        fundamentals = fetch_fundamentals(tuple(features["YahooTicker"].tolist()))
    features = features.merge(fundamentals, on="YahooTicker", how="left")

sector_options = sorted(features["Secteur"].dropna().unique().tolist())
filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
with filter_col1:
    sectors = st.multiselect("Secteurs", sector_options, default=sector_options)
with filter_col2:
    rsi_range = st.slider("RSI 14", 0.0, 100.0, (0.0, 100.0), 1.0)
with filter_col3:
    min_relative_volume = st.slider("Volume relatif minimum", 0.0, 5.0, 0.0, 0.1)
with filter_col4:
    trend_filter = st.multiselect("Signal", ["Haussier", "Neutre", "Baissier"], default=["Haussier", "Neutre", "Baissier"])

extra_col1, extra_col2, extra_col3, extra_col4 = st.columns(4)
with extra_col1:
    above_sma50 = st.checkbox("Prix au-dessus SMA50")
with extra_col2:
    above_sma200 = st.checkbox("Prix au-dessus SMA200")
with extra_col3:
    min_momentum_1m = st.number_input("Momentum 1 mois min. (%)", value=-100.0, step=1.0)
with extra_col4:
    max_volatility = st.number_input("Volatilité max. (%)", value=200.0, step=5.0)

result = features[
    features["Secteur"].isin(sectors)
    & features["Variation"].between(min_change, max_change, inclusive="both")
    & features["RSI14"].between(rsi_range[0], rsi_range[1], inclusive="both")
    & (features["VolumeRelatif"].fillna(0) >= min_relative_volume)
    & features["Signal"].isin(trend_filter)
    & (features["Momentum1M"].fillna(-999) >= min_momentum_1m)
    & (features["Volatilite20"].fillna(0) <= max_volatility)
].copy()

if symbol_search:
    query = _clean_symbol(symbol_search)
    raw_query = str(symbol_search).strip().lower()
    if exact_symbol_only and query:
        result = result[(result["__TickerClean"] == query) | (result["__YahooClean"] == query)].copy()
    else:
        result = result[
            result["Ticker"].astype(str).str.lower().str.contains(raw_query, na=False)
            | result.get("YahooTicker", result["Ticker"]).astype(str).str.lower().str.contains(raw_query, na=False)
            | result["Nom"].astype(str).str.lower().str.contains(raw_query, na=False)
            | result["Secteur"].astype(str).str.lower().str.contains(raw_query, na=False)
        ].copy()

if above_sma50:
    result = result[result["AboveSMA50"]]
if above_sma200:
    result = result[result["AboveSMA200"]]
if preset != "Tous":
    if preset in {"Dividendes élevés", "Valorisation faible"} and not load_fundamentals:
        st.warning("Active le chargement des fondamentaux pour ce filtre.")
    else:
        result = apply_screener_preset(result, preset)

if load_fundamentals:
    fund_col1, fund_col2, fund_col3 = st.columns(3)
    with fund_col1:
        pe_max = st.number_input("P/E maximum", value=100.0, min_value=0.0)
    with fund_col2:
        dividend_min = st.number_input("Dividende minimum (%)", value=0.0, min_value=0.0)
    with fund_col3:
        market_cap_min = st.number_input("Capitalisation min. (G$)", value=0.0, min_value=0.0)
    result = result[
        (result["PE"].isna() | (result["PE"] <= pe_max))
        & (result["DividendYield"].fillna(0) >= dividend_min)
        & (result["MarketCap"].fillna(0) >= market_cap_min * 1_000_000_000)
    ]

sort_options = {
    "Variation du jour": "Variation",
    "Momentum 1 mois": "Momentum1M",
    "Momentum 3 mois": "Momentum3M",
    "Volume relatif": "VolumeRelatif",
    "RSI": "RSI14",
    "Volatilité": "Volatilite20",
}
if load_fundamentals:
    sort_options.update({"P/E": "PE", "Dividende": "DividendYield", "Capitalisation": "MarketCap"})

sort_col1, sort_col2 = st.columns([2, 1])
with sort_col1:
    sort_label = st.selectbox("Trier par", list(sort_options))
with sort_col2:
    descending = st.toggle("Ordre décroissant", value=True)
result = result.sort_values(sort_options[sort_label], ascending=not descending, na_position="last")

st.metric("Titres correspondant aux critères", len(result))
base_columns = [
    "Ticker", "Nom", "Secteur", "Prix", "Variation", "RSI14", "Momentum1M",
    "Momentum3M", "VolumeRelatif", "Volatilite20", "DistanceHigh52", "Signal",
]
if load_fundamentals:
    base_columns += ["PE", "ForwardPE", "DividendYield", "MarketCap", "Beta"]
base_columns = [column for column in base_columns if column in result]

display_result = result[base_columns].head(mobile_page_limit(220, 70))
if len(result) > len(display_result):
    st.caption(f"Affichage limité à {len(display_result)} titres pour préserver la fluidité. Télécharge la liste complète pour obtenir tous les résultats.")

screener_table_config = {
    "Prix": st.column_config.NumberColumn(format="$%.2f"),
    "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
    "RSI14": st.column_config.NumberColumn("RSI", format="%.1f"),
    "Momentum1M": st.column_config.NumberColumn("Mom. 1M", format="%+.2f%%"),
    "Momentum3M": st.column_config.NumberColumn("Mom. 3M", format="%+.2f%%"),
    "VolumeRelatif": st.column_config.NumberColumn("Vol. relatif", format="%.2fx"),
    "Volatilite20": st.column_config.NumberColumn("Volatilité", format="%.1f%%"),
    "DistanceHigh52": st.column_config.NumberColumn("Écart sommet 52s", format="%+.1f%%"),
    "DividendYield": st.column_config.NumberColumn("Dividende", format="%.2f%%"),
    "MarketCap": st.column_config.NumberColumn("Capitalisation", format="compact"),
}

screener_table_event = None
try:
    screener_table_event = st.dataframe(
        display_result,
        hide_index=True,
        width="stretch",
        height=620,
        column_config=screener_table_config,
        on_select="rerun",
        selection_mode="single-row",
        key="screener_live_selectable_table",
    )
except TypeError:
    st.dataframe(
        display_result,
        hide_index=True,
        width="stretch",
        height=620,
        column_config=screener_table_config,
    )

selected_live_row = None
try:
    selected_rows = list(screener_table_event.selection.rows) if screener_table_event is not None else []
    if selected_rows:
        selected_live_row = display_result.iloc[int(selected_rows[0])]
except Exception:
    selected_live_row = None

if selected_live_row is not None:
    selected_symbol = str(selected_live_row.get("Ticker", ""))
    full_match = result[result["Ticker"].astype(str) == selected_symbol].head(1)
    source_row = full_match.iloc[0] if not full_match.empty else selected_live_row
    live_payload = {
        "ticker": selected_symbol,
        "yahoo": str(source_row.get("YahooTicker", selected_symbol)),
        "name": str(source_row.get("Nom", "")),
        "sector": str(source_row.get("Secteur", "")),
    }
    remember_live_selection(live_payload)
    render_live_quote_panel(
        live_payload["yahoo"],
        symbol=live_payload["ticker"],
        name=live_payload["name"],
        sector=live_payload["sector"],
        key_prefix="screener_table_live",
        compact=True,
    )

if not display_result.empty:
    st.markdown("#### Continuer l’analyse")
    action_options = [
        f"{row.get('Ticker', '')} — {row.get('Nom', '')}"
        for _, row in display_result.head(80).iterrows()
    ]
    selected_action = st.selectbox(
        "Choisir un titre dans les résultats",
        action_options,
        index=0 if bridge_symbol and action_options else None,
        placeholder="Sélectionner un titre…",
        key="screener_continue_action_selector",
    )
    if selected_action:
        selected_symbol = selected_action.split(" — ", 1)[0].strip()
        selected_row = display_result[display_result["Ticker"].astype(str) == selected_symbol].head(1)
        if not selected_row.empty:
            row = selected_row.iloc[0]
            yahoo = str(row.get("YahooTicker", selected_symbol)) if "YahooTicker" in row.index else selected_symbol
            live_payload = {
                "ticker": selected_symbol,
                "yahoo": yahoo,
                "name": str(row.get("Nom", "")),
                "sector": str(row.get("Secteur", "")),
            }
            remember_live_selection(live_payload)
            render_live_quote_panel(
                yahoo,
                symbol=selected_symbol,
                name=live_payload["name"],
                sector=live_payload["sector"],
                key_prefix="screener_selector_live",
                compact=True,
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("Mode Focus", key="screener_continue_focus", width="stretch"):
                    _route_symbol(selected_symbol, yahoo, "Focus")
            with c2:
                if st.button("Insiders", key="screener_continue_insiders", width="stretch"):
                    _route_symbol(selected_symbol, yahoo, "Insiders")
            with c3:
                if st.button("Alerte", key="screener_continue_alert", width="stretch"):
                    _route_symbol(selected_symbol, yahoo, "Alertes")
            with c4:
                if st.button("Liste", key="screener_continue_watchlist", width="stretch"):
                    _route_symbol(selected_symbol, yahoo, "Watchlist")

st.download_button(
    "Télécharger les résultats",
    data=result[base_columns].to_csv(index=False).encode("utf-8-sig"),
    file_name=f"screener_{current_universe().short_label.lower().replace(' ', '_')}.csv",
    mime="text/csv",
)

footer()
