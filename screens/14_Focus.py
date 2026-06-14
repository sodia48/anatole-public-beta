from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.ai import analyze_stock_in_french
from core.analytics import add_indicators, enrich_news, explain_move
from core.charts import price_chart
from core.data import (
    fetch_company_info,
    fetch_dividend_history,
    fetch_history,
    fetch_insider_transactions,
    fetch_recommendation_summary,
    fetch_stock_news,
    load_constituents,
)
from core.database import add_watchlist
from core.pro_chart import build_event_markers, render_professional_chart
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import format_compact, format_money, format_number, get_secret, safe_float


configure_page("Fiche action", "📊")
apply_style()
profile = sidebar_context()
page_header(
    "Fiche action",
    "Un actif à la fois : graphique, finances, actualités et données avancées chargées à la demande.",
)

constituents, _ = load_constituents()
lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))
options = constituents["YahooTicker"].tolist()
default = st.session_state.get("selected_ticker", "RY.TO")
if default not in options:
    default = options[0]

controls = st.columns([2.4, 1, 1])
with controls[0]:
    ticker = st.selectbox(
        "Titre",
        options,
        index=options.index(default),
        format_func=lambda value: lookup.get(value, value),
    )
with controls[1]:
    periods = ["3mo", "6mo", "1y", "2y", "5y"]
    preferred = st.session_state.get("default_period", "1y")
    period = st.selectbox("Période", periods, index=periods.index(preferred) if preferred in periods else 2)
with controls[2]:
    interval = st.selectbox("Intervalle", ["1d", "1wk"], index=0)

st.session_state.selected_ticker = ticker

with st.spinner("Chargement du graphique…"):
    history = add_indicators(fetch_history(ticker, period, interval))
info = fetch_company_info(ticker)
name = info.get("longName") or info.get("shortName") or ticker
currency = info.get("currency", "CAD")

if history.empty:
    st.warning("Historique indisponible pour ce titre.")
    footer()
    st.stop()

last = history.iloc[-1]
previous = history.iloc[-2] if len(history) > 1 else last
price = safe_float(last.get("Close"))
previous_close = safe_float(previous.get("Close"))
change = ((price - previous_close) / previous_close * 100) if previous_close else np.nan

st.subheader(f"{name} · {ticker}")
metrics = st.columns(6)
metrics[0].metric("Cours", format_money(price, currency), f"{change:+.2f}%" if not np.isnan(change) else None)
metrics[1].metric("Capitalisation", format_compact(info.get("marketCap")))
metrics[2].metric("P/E", format_number(info.get("trailingPE")))
metrics[3].metric("Rendement", f"{safe_float(info.get('dividendYield')) * 100:.2f}%" if not np.isnan(safe_float(info.get("dividendYield"))) else "N/D")
metrics[4].metric("RSI 14", format_number(last.get("RSI14"), 1))
metrics[5].metric("Volume", format_compact(last.get("Volume")))

buttons = st.columns([1, 1, 4])
with buttons[0]:
    if st.button("Ajouter à la watchlist", width="stretch"):
        add_watchlist(profile, ticker)
        st.success("Titre ajouté à la watchlist.")
with buttons[1]:
    st.page_link("screens/4_Alertes.py", label="Créer une alerte", width="stretch")

show_markers = st.toggle(
    "Afficher les événements sur le graphique",
    value=bool(st.session_state.get("show_event_markers", False)),
    help="Les actualités ne sont chargées que lorsque cette option est activée.",
)
news_raw_for_chart = fetch_stock_news(ticker) if show_markers else []
markers = build_event_markers(news_raw_for_chart)
price_lines = []
if not np.isnan(safe_float(info.get("targetMeanPrice"))):
    price_lines.append({"price": safe_float(info.get("targetMeanPrice")), "title": "Cible analystes", "color": "#F59E0B"})

compatibility_mode = st.toggle(
    "Utiliser le graphique Plotly",
    value=False,
    help="Active ce mode si le graphique professionnel est bloqué par le réseau.",
)
if compatibility_mode:
    st.plotly_chart(price_chart(history, ticker, ["SMA 20", "SMA 50"]), width="stretch", key=f"focus_plotly_compat_{ticker}_{period}_{interval}")
else:
    render_professional_chart(
        history,
        ticker,
        markers=markers,
        price_lines=price_lines,
        height=720,
        dark=bool(st.session_state.get("theme_toggle", False)),
        key=f"focus_minimal_{ticker}_{period}_{interval}",
    )

section = st.segmented_control(
    "Section",
    ["Aperçu", "Finances", "Actualités", "Données avancées", "Analyse"],
    default="Aperçu",
    selection_mode="single",
    label_visibility="collapsed",
)

if section == "Aperçu":
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SMA 20", format_money(last.get("SMA20"), currency))
    c2.metric("SMA 50", format_money(last.get("SMA50"), currency))
    c3.metric("SMA 200", format_money(last.get("SMA200"), currency))
    relative_volume = safe_float(last.get("Volume")) / max(float(history["Volume"].tail(20).mean() or 1), 1)
    c4.metric("Volume relatif", f"{relative_volume:.2f}x")

    feature = pd.Series(
        {
            "Variation": change,
            "RelativeVolume": relative_volume,
            "RSI14": safe_float(last.get("RSI14")),
            "MACD": safe_float(last.get("MACD")),
            "SignalMACD": safe_float(last.get("SignalMACD")),
            "Close": price,
            "SMA20": safe_float(last.get("SMA20")),
            "SMA50": safe_float(last.get("SMA50")),
            "SMA200": safe_float(last.get("SMA200")),
        }
    )
    st.caption("Facteurs potentiels détectés automatiquement; ils ne prouvent pas la cause du mouvement.")
    for index, reason in enumerate(explain_move(feature, 0.0, pd.DataFrame()), 1):
        st.write(f"**{index}.** {reason}")

    with st.expander("Indicateurs Plotly avancés", expanded=False):
        overlays = st.multiselect(
            "Superpositions",
            ["SMA 20", "SMA 50", "SMA 200", "EMA 20", "Bandes de Bollinger"],
            default=["SMA 20", "SMA 50"],
        )
        st.plotly_chart(price_chart(history, ticker, overlays), width="stretch", key=f"focus_plotly_advanced_{ticker}_{period}_{interval}_{hash(tuple(overlays))}")

elif section == "Finances":
    rows = [
        ("Secteur", info.get("sector", "N/D")),
        ("Industrie", info.get("industry", "N/D")),
        ("P/E historique", format_number(info.get("trailingPE"))),
        ("P/E anticipé", format_number(info.get("forwardPE"))),
        ("Prix / valeur comptable", format_number(info.get("priceToBook"))),
        ("Valeur d'entreprise", format_compact(info.get("enterpriseValue"))),
        ("Marge bénéficiaire", f"{safe_float(info.get('profitMargins')) * 100:.2f}%" if not np.isnan(safe_float(info.get("profitMargins"))) else "N/D"),
        ("Croissance du chiffre d'affaires", f"{safe_float(info.get('revenueGrowth')) * 100:.2f}%" if not np.isnan(safe_float(info.get("revenueGrowth"))) else "N/D"),
        ("Dette / capitaux propres", format_number(info.get("debtToEquity"))),
        ("Flux de trésorerie disponible", format_compact(info.get("freeCashflow"))),
        ("Cible moyenne", format_money(info.get("targetMeanPrice"), currency)),
        ("Plus haut 52 semaines", format_money(info.get("fiftyTwoWeekHigh"), currency)),
        ("Plus bas 52 semaines", format_money(info.get("fiftyTwoWeekLow"), currency)),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Indicateur", "Valeur"]), hide_index=True, width="stretch")
    if info.get("longBusinessSummary"):
        st.subheader("Activités")
        st.write(info["longBusinessSummary"])

elif section == "Actualités":
    with st.spinner("Chargement des actualités…"):
        news = enrich_news(fetch_stock_news(ticker))
    if news.empty:
        st.info("Aucune actualité récente n'a été retournée.")
    else:
        sentiment = news["SentimentScore"].mean() * 100
        st.metric("Sentiment moyen", f"{sentiment:+.0f}/100")
        for _, article in news.head(12).iterrows():
            st.markdown(f"**[{article['Titre']}]({article['URL']})**")
            st.caption(f"{article['Source']} · {article['Categorie']} · {article['Sentiment']} · {article['Date']}")
            if article.get("Resume"):
                st.write(article["Resume"])
            st.divider()

elif section == "Données avancées":
    st.caption("Ces données sont chargées uniquement sur cette page afin de préserver la rapidité du reste de l'application.")
    if st.button("Charger les données avancées", type="primary"):
        st.session_state[f"advanced_loaded_{ticker}"] = True

    if st.session_state.get(f"advanced_loaded_{ticker}"):
        with st.spinner("Chargement des dividendes, analystes et initiés…"):
            dividends = fetch_dividend_history(ticker)
            recommendations = fetch_recommendation_summary(ticker)
            insiders = fetch_insider_transactions(ticker)

        st.subheader("Historique des dividendes")
        if dividends.empty:
            st.info("Aucun historique de dividendes disponible.")
        else:
            st.line_chart(dividends.set_index("Date")["Dividende"], height=280)
            st.dataframe(dividends.tail(20), hide_index=True, width="stretch")

        st.subheader("Consensus des analystes")
        if recommendations.empty:
            st.info("Le consensus détaillé n'est pas disponible.")
        else:
            st.dataframe(recommendations, hide_index=True, width="stretch")

        st.subheader("Transactions d'initiés")
        if insiders.empty:
            st.info("Aucune donnée d'initiés disponible auprès de la source.")
        else:
            st.dataframe(insiders.head(30), hide_index=True, width="stretch")

elif section == "Analyse":
    st.subheader("Scénarios")
    st.write("**Haussier :** croissance et révisions positives, avec maintien du prix au-dessus des moyennes mobiles principales.")
    st.write("**Central :** consolidation autour des moyennes mobiles, avec volatilité proche de la normale.")
    st.write("**Baissier :** ralentissement des résultats, révisions négatives ou rupture des supports récents.")

    openai_key = get_secret("OPENAI_API_KEY")
    model = get_secret("OPENAI_MODEL", "gpt-5.5")
    if not openai_key:
        st.info("Ajoute OPENAI_API_KEY dans .streamlit/secrets.toml pour activer l'analyse contextuelle.")
    elif st.button("Générer une analyse contextuelle", type="primary"):
        with st.spinner("Analyse en cours…"):
            news = enrich_news(fetch_stock_news(ticker))
            technical = {
                "RSI14": safe_float(last.get("RSI14")),
                "MACD": safe_float(last.get("MACD")),
                "SignalMACD": safe_float(last.get("SignalMACD")),
                "SMA20": safe_float(last.get("SMA20")),
                "SMA50": safe_float(last.get("SMA50")),
                "SMA200": safe_float(last.get("SMA200")),
            }
            st.session_state[f"focus_ai_{ticker}"] = analyze_stock_in_french(
                ticker=ticker,
                company_name=name,
                market_data={"prix": price, "variation_jour": change, "volume": safe_float(last.get("Volume")), "source": "Yahoo Finance"},
                fundamentals=info,
                technical=technical,
                news=news,
                api_key=openai_key,
                model=model,
            )
    if st.session_state.get(f"focus_ai_{ticker}"):
        st.markdown(st.session_state[f"focus_ai_{ticker}"])
        st.caption("Analyse informative pouvant contenir des erreurs; elle ne constitue pas un conseil financier.")

footer()
