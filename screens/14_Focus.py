from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.ai import analyze_stock_in_french
from core.analytics import add_indicators, enrich_news, explain_move
from core.charts import DEFAULT_PLOTLY_OVERLAYS, price_chart
from core.data import (
    fetch_analyst_consensus,
    fetch_company_financials,
    fetch_company_info,
    fetch_dividend_history,
    fetch_history,
    fetch_insider_activity,
    fetch_stock_news,
    load_constituents,
)
from core.database import add_watchlist
from core.pro_chart import build_event_markers
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import format_compact, format_money, format_number, get_secret, safe_float


def percent_text(value: object, decimals: int = 2) -> str:
    number = safe_float(value)
    if np.isnan(number):
        return "N/D"
    return f"{number * 100:.{decimals}f}%"


def ratio_text(value: object, decimals: int = 2) -> str:
    number = safe_float(value)
    return "N/D" if np.isnan(number) else f"{number:.{decimals}f}x"


def financial_value(bundle: dict, key: str) -> float:
    return safe_float(bundle.get("metrics", {}).get(key, {}).get("value"))


def local_analysis_lines(
    price: float,
    last: pd.Series,
    info: dict,
) -> list[str]:
    lines: list[str] = []
    rsi = safe_float(last.get("RSI14"))
    sma20 = safe_float(last.get("SMA20"))
    sma50 = safe_float(last.get("SMA50"))
    sma200 = safe_float(last.get("SMA200"))

    if not np.isnan(rsi):
        if rsi >= 70:
            lines.append(f"Le RSI 14 est élevé ({rsi:.1f}), ce qui signale un momentum fort mais un risque de surachat.")
        elif rsi <= 30:
            lines.append(f"Le RSI 14 est faible ({rsi:.1f}), ce qui signale une pression vendeuse et une possible zone de survente.")
        else:
            lines.append(f"Le RSI 14 est neutre ({rsi:.1f}).")

    averages = []
    for label, value in (("SMA 20", sma20), ("SMA 50", sma50), ("SMA 200", sma200)):
        if not np.isnan(value):
            averages.append(f"au-dessus de {label}" if price >= value else f"sous {label}")
    if averages:
        lines.append("Le cours se situe " + ", ".join(averages) + ".")

    revenue_growth = safe_float(info.get("revenueGrowth"))
    earnings_growth = safe_float(info.get("earningsGrowth"))
    margin = safe_float(info.get("profitMargins"))
    if not np.isnan(revenue_growth):
        lines.append(f"La croissance récente du chiffre d'affaires est de {revenue_growth * 100:+.1f}%.")
    if not np.isnan(earnings_growth):
        lines.append(f"La croissance récente des bénéfices est de {earnings_growth * 100:+.1f}%.")
    if not np.isnan(margin):
        lines.append(f"La marge bénéficiaire publiée est de {margin * 100:.1f}%.")

    return lines or ["La lecture automatique est limitée aux données de marché actuellement disponibles."]


configure_page("Fiche action", "📊")
apply_style()
profile = sidebar_context()
page_header(
    "Fiche action",
    "Un actif à la fois : graphique, finances, actualités, analystes et transactions d'initiés.",
)

constituents, _ = load_constituents()
lookup = dict(
    zip(
        constituents["YahooTicker"],
        constituents["Ticker"] + " — " + constituents["Nom"],
    )
)
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
    period = st.selectbox(
        "Période",
        periods,
        index=periods.index(preferred) if preferred in periods else 2,
    )
with controls[2]:
    interval = st.selectbox("Intervalle", ["1d", "1wk"], index=0)

st.session_state.selected_ticker = ticker
selected_row = constituents.loc[constituents["YahooTicker"] == ticker].head(1)
fallback_name = (
    str(selected_row.iloc[0]["Nom"])
    if not selected_row.empty
    else ticker
)
fallback_sector = (
    str(selected_row.iloc[0]["Secteur"])
    if not selected_row.empty
    else "N/D"
)

with st.spinner("Chargement du graphique…"):
    history = add_indicators(fetch_history(ticker, period, interval))
info = fetch_company_info(ticker)
name = info.get("longName") or info.get("shortName") or fallback_name
currency = info.get("currency", "CAD")

if history.empty:
    st.warning("Historique indisponible pour ce titre.")
    footer()
    st.stop()

last = history.iloc[-1]
previous = history.iloc[-2] if len(history) > 1 else last
price = safe_float(last.get("Close"))
previous_close = safe_float(previous.get("Close"))
change = (
    ((price - previous_close) / previous_close * 100)
    if previous_close
    else np.nan
)

st.subheader(f"{name} · {ticker}")
metrics = st.columns(6)
metrics[0].metric(
    "Cours",
    format_money(price, currency),
    f"{change:+.2f}%" if not np.isnan(change) else None,
)
metrics[1].metric("Capitalisation", format_compact(info.get("marketCap")))
metrics[2].metric("P/E", format_number(info.get("trailingPE")))
metrics[3].metric("Rendement", percent_text(info.get("dividendYield")))
metrics[4].metric("RSI 14", format_number(last.get("RSI14"), 1))
metrics[5].metric("Volume", format_compact(last.get("Volume")))

buttons = st.columns([1, 1, 4])
with buttons[0]:
    if st.button("Ajouter à la watchlist", width="stretch"):
        add_watchlist(profile, ticker)
        st.success("Titre ajouté à la watchlist.")
with buttons[1]:
    st.page_link(
        "screens/4_Alertes.py",
        label="Créer une alerte",
        width="stretch",
    )

show_markers = st.toggle(
    "Afficher les événements sur le graphique",
    value=bool(st.session_state.get("show_event_markers", False)),
    help="Les actualités ne sont chargées que lorsque cette option est activée.",
)
news_raw_for_chart = fetch_stock_news(ticker) if show_markers else []
markers = build_event_markers(news_raw_for_chart)
price_lines = []
if not np.isnan(safe_float(info.get("targetMeanPrice"))):
    price_lines.append(
        {
            "price": safe_float(info.get("targetMeanPrice")),
            "title": "Cible analystes",
            "color": "#F59E0B",
        }
    )

# Graphique Plotly intégré automatiquement.
# Aucun bouton d'activation n'est nécessaire pour l'utilisateur.
st.caption(
    "Graphique technique automatique : chandeliers, volume, moyennes mobiles, "
    "EMA 20 et bandes de Bollinger lorsque les données sont disponibles."
)
st.plotly_chart(
    price_chart(history, ticker, DEFAULT_PLOTLY_OVERLAYS),
    width="stretch",
    key=f"focus_plotly_auto_{ticker}_{period}_{interval}",
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
    relative_volume = safe_float(last.get("Volume")) / max(
        float(history["Volume"].tail(20).mean() or 1),
        1,
    )
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
    st.caption(
        "Facteurs potentiels détectés automatiquement; ils ne prouvent pas la cause du mouvement."
    )
    for index, reason in enumerate(
        explain_move(feature, 0.0, pd.DataFrame()),
        1,
    ):
        st.write(f"**{index}.** {reason}")

    st.info(
        "Les indicateurs Plotly sont intégrés automatiquement au graphique principal "
        "plus haut : SMA 20, SMA 50, SMA 200, EMA 20, volume et bandes de Bollinger "
        "lorsque les données sont disponibles."
    )

elif section == "Finances":
    with st.spinner("Chargement des informations financières…"):
        financials = fetch_company_financials(ticker)
    financial_info = financials.get("info", {})

    st.subheader("Indicateurs financiers essentiels")
    top = st.columns(6)
    top[0].metric("Chiffre d'affaires", format_compact(financial_value(financials, "revenue")))
    top[1].metric("Résultat net", format_compact(financial_value(financials, "net_income")))
    top[2].metric("Flux disponible", format_compact(financial_value(financials, "free_cashflow")))
    top[3].metric("Dette totale", format_compact(financial_value(financials, "debt")))
    top[4].metric("Marge nette", percent_text(financial_value(financials, "profit_margin")))
    top[5].metric("Ratio courant", ratio_text(financial_value(financials, "current_ratio")))

    period_high = safe_float(history.get("High", pd.Series(dtype=float)).max())
    period_low = safe_float(history.get("Low", pd.Series(dtype=float)).min())
    period_performance = (
        ((price / safe_float(history.iloc[0].get("Close"))) - 1)
        if safe_float(history.iloc[0].get("Close"))
        else np.nan
    )

    rows = [
        ("Secteur", financial_info.get("sector") or fallback_sector),
        ("Industrie", financial_info.get("industry") or "Non classée"),
        ("Capitalisation", format_compact(financial_info.get("marketCap"))),
        ("Valeur d'entreprise", format_compact(financial_info.get("enterpriseValue"))),
        ("P/E historique", format_number(financial_info.get("trailingPE"))),
        ("P/E anticipé", format_number(financial_info.get("forwardPE"))),
        ("Prix / valeur comptable", format_number(financial_info.get("priceToBook"))),
        ("Croissance du chiffre d'affaires", percent_text(financial_value(financials, "revenue_growth"))),
        ("Croissance des bénéfices", percent_text(financial_value(financials, "earnings_growth"))),
        ("Rendement des capitaux propres", percent_text(financial_value(financials, "return_on_equity"))),
        ("Rendement de l'actif", percent_text(financial_value(financials, "return_on_assets"))),
        ("Dette / capitaux propres", format_number(financial_info.get("debtToEquity"))),
        ("Trésorerie", format_compact(financial_value(financials, "cash"))),
        ("Capitaux propres", format_compact(financial_value(financials, "equity"))),
        ("Plus haut 52 semaines", format_money(financial_info.get("fiftyTwoWeekHigh") or period_high, currency)),
        ("Plus bas 52 semaines", format_money(financial_info.get("fiftyTwoWeekLow") or period_low, currency)),
        ("Performance de la période affichée", percent_text(period_performance)),
    ]
    st.dataframe(
        pd.DataFrame(rows, columns=["Indicateur", "Valeur"]),
        hide_index=True,
        width="stretch",
    )

    statements_available = False
    for title, key in (
        ("Compte de résultat annuel", "income"),
        ("Bilan annuel", "balance"),
        ("Flux de trésorerie annuels", "cashflow"),
    ):
        table = financials.get(key, pd.DataFrame())
        if isinstance(table, pd.DataFrame) and not table.empty:
            statements_available = True
            with st.expander(title, expanded=False):
                st.dataframe(table, hide_index=True, width="stretch")

    if not statements_available:
        st.caption(
            "Les états financiers détaillés ne sont pas retournés pour ce titre; "
            "les données de marché et les principaux ratios disponibles restent affichés."
        )

    if financial_info.get("longBusinessSummary"):
        st.subheader("Activités")
        st.write(financial_info["longBusinessSummary"])

    available_rows = sum(value != "N/D" for _, value in rows)
    st.caption(
        f"Couverture : {available_rows}/{len(rows)} indicateurs disponibles. "
        f"Sources : {financials.get('source', 'Données de marché')}. "
        "Les valeurs peuvent être différées ou révisées."
    )

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
            st.caption(
                f"{article['Source']} · {article['Categorie']} · "
                f"{article['Sentiment']} · {article['Date']}"
            )
            if article.get("Resume"):
                st.write(article["Resume"])
            st.divider()

elif section == "Données avancées":
    st.caption(
        "Analystes, dividendes et initiés sont chargés uniquement dans cette section "
        "afin de préserver la rapidité du reste de l'application."
    )
    with st.spinner("Chargement des dividendes, analystes et initiés…"):
        dividends = fetch_dividend_history(ticker)
        analyst = fetch_analyst_consensus(ticker)
        insider = fetch_insider_activity(ticker)

    st.subheader("Historique des dividendes")
    if dividends.empty:
        st.caption("Aucun dividende n'a été retourné pour la période disponible.")
    else:
        st.line_chart(dividends.set_index("Date")["Dividende"], height=280)
        st.dataframe(dividends.tail(20), hide_index=True, width="stretch")

    st.subheader("Consensus des analystes")
    analyst_metrics = analyst.get("metrics", {})
    analyst_cols = st.columns(4)
    analyst_cols[0].metric(
        "Consensus",
        analyst_metrics.get("recommendation", "Non couvert"),
    )
    analyst_cols[1].metric(
        "Cible moyenne",
        format_money(analyst_metrics.get("target_mean"), currency),
    )
    analyst_cols[2].metric(
        "Potentiel moyen",
        percent_text(analyst_metrics.get("upside_mean")),
    )
    analyst_count = safe_float(analyst_metrics.get("analyst_count"))
    analyst_cols[3].metric(
        "Analystes",
        "N/D" if np.isnan(analyst_count) else f"{analyst_count:.0f}",
    )

    targets = pd.DataFrame(
        [
            ("Cible basse", format_money(analyst_metrics.get("target_low"), currency)),
            ("Cible médiane", format_money(analyst_metrics.get("target_median"), currency)),
            ("Cible moyenne", format_money(analyst_metrics.get("target_mean"), currency)),
            ("Cible haute", format_money(analyst_metrics.get("target_high"), currency)),
            ("Cours de référence", format_money(analyst_metrics.get("current_price") or price, currency)),
            ("Note numérique", format_number(analyst_metrics.get("recommendation_mean"))),
        ],
        columns=["Mesure", "Valeur"],
    )
    st.dataframe(targets, hide_index=True, width="stretch")

    analyst_summary = analyst.get("summary", pd.DataFrame())
    if isinstance(analyst_summary, pd.DataFrame) and not analyst_summary.empty:
        st.markdown("#### Répartition des recommandations")
        st.dataframe(analyst_summary.head(12), hide_index=True, width="stretch")

    upgrades = analyst.get("upgrades", pd.DataFrame())
    if isinstance(upgrades, pd.DataFrame) and not upgrades.empty:
        with st.expander("Changements récents de recommandation", expanded=False):
            st.dataframe(upgrades.head(20), hide_index=True, width="stretch")

    st.caption(f"Source : {analyst.get('source', 'Données de marché')}. La couverture varie selon l'entreprise.")

    st.subheader("Transactions d'initiés")
    ownership = insider.get("ownership", {})
    owner_cols = st.columns(4)
    owner_cols[0].metric("Détention des initiés", percent_text(ownership.get("held_percent_insiders")))
    owner_cols[1].metric("Détention institutionnelle", percent_text(ownership.get("held_percent_institutions")))
    owner_cols[2].metric("Actions en circulation", format_compact(ownership.get("shares_outstanding")))
    owner_cols[3].metric("Flottant", format_compact(ownership.get("float_shares")))

    transactions = insider.get("transactions", pd.DataFrame())
    purchases = insider.get("purchases", pd.DataFrame())
    roster = insider.get("roster", pd.DataFrame())

    if isinstance(transactions, pd.DataFrame) and not transactions.empty:
        st.markdown("#### Transactions récentes")
        st.dataframe(transactions.head(40), hide_index=True, width="stretch")
    elif isinstance(purchases, pd.DataFrame) and not purchases.empty:
        st.markdown("#### Activité agrégée des initiés")
        st.dataframe(purchases, hide_index=True, width="stretch")
    else:
        st.caption(
            "Aucune transaction détaillée n'est retournée par Yahoo pour ce titre. "
            "Anatole affiche néanmoins l'actionnariat interne et les dirigeants disponibles."
        )

    if isinstance(roster, pd.DataFrame) and not roster.empty:
        with st.expander("Dirigeants et initiés déclarés", expanded=False):
            st.dataframe(roster.head(30), hide_index=True, width="stretch")

    st.link_button(
        "Consulter les déclarations officielles canadiennes dans SEDI",
        insider.get("official_url", "https://www.sedi.ca/sedi/SVTReportsAccessController"),
        width="stretch",
    )
    st.caption(
        f"Source de synthèse : {insider.get('source', 'Yahoo Finance')}. "
        "SEDI demeure la source officielle des déclarations d'initiés au Canada."
    )

elif section == "Analyse":
    st.subheader("Scénarios")
    st.write(
        "**Haussier :** croissance et révisions positives, avec maintien du prix "
        "au-dessus des moyennes mobiles principales."
    )
    st.write(
        "**Central :** consolidation autour des moyennes mobiles, avec volatilité "
        "proche de la normale."
    )
    st.write(
        "**Baissier :** ralentissement des résultats, révisions négatives ou rupture "
        "des supports récents."
    )

    st.subheader("Lecture automatique")
    for line in local_analysis_lines(price, last, info):
        st.write(f"- {line}")

    openai_key = get_secret("OPENAI_API_KEY")
    model = get_secret("OPENAI_MODEL", "gpt-5.5")
    if openai_key and st.button("Approfondir l'analyse contextuelle", type="primary"):
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
                market_data={
                    "prix": price,
                    "variation_jour": change,
                    "volume": safe_float(last.get("Volume")),
                    "source": "Yahoo Finance",
                },
                fundamentals=info,
                technical=technical,
                news=news,
                api_key=openai_key,
                model=model,
            )
    if st.session_state.get(f"focus_ai_{ticker}"):
        st.markdown(st.session_state[f"focus_ai_{ticker}"])
        st.caption(
            "Analyse informative pouvant contenir des erreurs; elle ne constitue pas un conseil financier."
        )

footer()
