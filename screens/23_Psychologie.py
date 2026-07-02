from __future__ import annotations

import streamlit as st

from core.analytics import add_indicators, enrich_news
from core.data import fetch_history, fetch_stock_news, load_constituents
from core.data_quality import render_data_quality_strip
from core.market_psychology import (
    market_psychology_score,
    psychology_components_frame,
    psychology_gauge_figure,
    psychology_summary_text,
    stock_psychology_score,
)
from core.performance import load_timer, perf_caption
from core.runtime import load_light_market_bundle
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.universe import current_universe

configure_page("Psychologie du marché", "🧠")
apply_style()
sidebar_context()
page_header(
    "Psychologie du marché",
    "Un indicateur psychologique interne inspiré du Fear & Greed, avec sources et mesure par titre.",
    "🧠",
)

section = st.segmented_control(
    "Vue",
    ["Marché", "Titre spécifique", "Méthodologie & sources"],
    default="Marché",
    selection_mode="single",
)

needs_market_data = section in {"Marché", "Titre spécifique"}
market = None
diagnostics = {}
if needs_market_data:
    with st.spinner("Lecture du pouls psychologique du marché…"):
        with load_timer("market_psychology"):
            constituents, diagnostics, market = load_light_market_bundle()
    perf_caption("market_psychology", threshold=2.0)

    if market.empty:
        st.warning("Les données de marché sont temporairement indisponibles.")
        footer()
        st.stop()

    render_data_quality_strip(market, diagnostics, compact=True)

if section == "Marché":
    result = market_psychology_score(market)
    score = float(result["score"])
    label = str(result["label"])

    left, right = st.columns([1.2, 1])
    with left:
        st.plotly_chart(psychology_gauge_figure(score, label), width="stretch", key="market_psychology_gauge")
    with right:
        st.metric("Indice psychologique marché", f"{score:.1f}/100", label)
        st.write(psychology_summary_text(result))
        st.caption(
            "Ce n'est pas le CNN Fear & Greed Index officiel. "
            "C'est une lecture propriétaire Anatole basée sur les données disponibles dans l'application."
        )

    st.subheader("Composantes du marché")
    components = psychology_components_frame(result)
    st.dataframe(
        components,
        hide_index=True,
        width="stretch",
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        },
    )

elif section == "Titre spécifique":
    st.caption("Mesure la psychologie d'un titre précis à partir de son prix, volume, tendance, RSI, nouvelles et force relative.")
    all_constituents, _ = load_constituents()
    options = all_constituents["YahooTicker"].tolist()
    default_ticker = st.session_state.get("selected_ticker", options[0] if options else "")
    if default_ticker not in options and options:
        default_ticker = options[0]

    ticker = st.selectbox(
        "Titre à analyser",
        options,
        index=options.index(default_ticker) if default_ticker in options else 0,
        format_func=lambda value: (
            all_constituents.loc[all_constituents["YahooTicker"] == value, "Ticker"].iloc[0]
            + " — "
            + all_constituents.loc[all_constituents["YahooTicker"] == value, "Nom"].iloc[0]
            if value in set(all_constituents["YahooTicker"]) else value
        ),
    )

    period = st.selectbox("Historique utilisé", ["6mo", "1y", "2y"], index=1)
    include_news = st.toggle(
        "Inclure les nouvelles dans le score",
        value=False,
        help="Les nouvelles peuvent ralentir le chargement. Active cette option seulement si tu veux les intégrer au score du titre.",
    )

    selected_row = all_constituents.loc[all_constituents["YahooTicker"] == ticker].head(1)
    stock_sector = selected_row["Secteur"].iloc[0] if not selected_row.empty and "Secteur" in selected_row else None

    with st.spinner(f"Calcul de la psychologie de {ticker}…"):
        history = add_indicators(fetch_history(ticker, period, "1d"))
        news = None
        if include_news:
            try:
                raw_news = fetch_stock_news(ticker)
                news = enrich_news(raw_news) if raw_news is not None else None
            except Exception:
                news = None

    if history.empty:
        st.warning("Historique indisponible pour ce titre.")
    else:
        stock_result = stock_psychology_score(ticker, history, market, news=news, stock_sector=stock_sector)
        stock_score = float(stock_result["score"])
        stock_label = str(stock_result["label"])

        left, right = st.columns([1.2, 1])
        with left:
            st.plotly_chart(psychology_gauge_figure(stock_score, stock_label), width="stretch", key=f"stock_psychology_gauge_{ticker}")
        with right:
            st.metric("Indice psychologique titre", f"{stock_score:.1f}/100", stock_label)
            st.write(psychology_summary_text(stock_result))
            st.caption(
                "Ce score mesure le comportement psychologique autour du titre, pas sa valeur fondamentale."
            )

        st.subheader("Composantes du titre")
        stock_components = psychology_components_frame(stock_result)
        st.dataframe(
            stock_components,
            hide_index=True,
            width="stretch",
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            },
        )

        with st.expander("Données utilisées pour ce titre"):
            st.write(
                "- Historique de prix et volume : données récupérées par Anatole via ses fournisseurs de marché existants."
            )
            st.write("- RSI, SMA50, SMA200 : calculs techniques locaux à partir de l'historique.")
            st.write("- Force relative : comparaison à la moyenne du secteur dans l'univers actif.")
            st.write("- Nouvelles : flux disponible dans Anatole, quand l'option est activée et que le fournisseur les retourne.")

else:
    st.subheader("Méthodologie")
    st.write(
        "L'indice psychologique Anatole est un indicateur propriétaire. "
        "Il ne copie pas le CNN Fear & Greed Index officiel. "
        "Il mesure le même type d'idée — peur, neutralité ou appétit pour le risque — mais avec les données disponibles dans Anatole."
    )

    st.markdown(
        """
        **Sources internes utilisées :**
        - snapshot marché Anatole : variations, secteurs, largeur du marché ;
        - historique réel de prix et volumes ;
        - indicateurs techniques calculés localement : SMA, RSI, volume relatif ;
        - nouvelles disponibles dans Anatole lorsque le fournisseur les retourne ;
        - comparaison sectorielle à partir de l'univers actif.
        """
    )

    st.info(
        "Chaque composante affiche maintenant sa source et le détail source. "
        "Quand une donnée manque, Anatole ramène la composante vers 50/100 au lieu d'inventer un signal."
    )

if market is not None:
    st.caption(f"Univers analysé : {current_universe().label} · {len(market)} titres suivis.")
else:
    st.caption(f"Univers actif : {current_universe().label}")

footer()