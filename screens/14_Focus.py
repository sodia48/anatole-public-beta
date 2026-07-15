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
from core.ecosystem import (
    affiliation_table,
    contribution_table,
    ecosystem_explainer,
    ecosystem_for_ticker,
    ecosystem_metrics,
    ecosystem_sankey,
)
from core.device import mobile_chart_height, mobile_is_lite
from core.performance import load_timer, perf_caption
from core.mobile_experience import plotly_config
from core.pro_chart import build_event_markers
from core.strategy_lab import (
    STRATEGIES,
    run_strategy_backtest,
    strategy_catalog_frame,
    strategy_equity_chart,
    strategy_options,
    strategy_signal_overlay,
)
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import format_compact, format_money, format_number, get_secret, safe_float
from core.trader_toolkit import (
    build_trader_dashboard,
    confluence_map,
    execution_ladder,
    institutional_trade_memo,
    position_sizing_table,
    risk_reward_matrix,
    scenario_table,
    setup_scorecards,
    smart_alert_recipes,
    timeframe_alignment_table,
    trade_plan,
    trader_checklist,
    trader_journal_template,
    trader_levels_table,
    trader_narrative,
)


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


def estimate_retail_share(ownership: dict[str, object]) -> float:
    institutions = safe_float(ownership.get("held_percent_institutions"))
    insiders = safe_float(ownership.get("held_percent_insiders"))
    if np.isnan(institutions) and np.isnan(insiders):
        return np.nan
    institutions = 0.0 if np.isnan(institutions) else institutions
    insiders = 0.0 if np.isnan(insiders) else insiders
    return max(0.0, min(1.0, 1.0 - institutions - insiders))


def volume_flow_label(last_open: object, last_close: object) -> str:
    open_value = safe_float(last_open)
    close_value = safe_float(last_close)
    if np.isnan(open_value) or np.isnan(close_value):
        return "N/D"
    return "Entrée dominante" if close_value >= open_value else "Sortie dominante"



def _ecosystem_layer(rows: pd.DataFrame, layer: str, limit: int = 5) -> pd.DataFrame:
    if rows.empty or "layer" not in rows.columns:
        return pd.DataFrame()
    return rows[rows["layer"].astype(str) == layer].head(limit).copy()


def _render_ecosystem_card(title: str, rows: pd.DataFrame, empty: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if rows.empty:
            st.caption(empty)
            return
        for _, row in rows.iterrows():
            confidence = str(row.get("confidence", "")).strip()
            source_name = str(row.get("source_name", "")).strip()
            source_url = str(row.get("source_url", "")).strip()
            badge = "Documenté" if confidence == "Documenté" else "Indicatif"
            st.markdown(f"**{row.get('relation', 'Relation')}**")
            st.write(str(row.get("entity", "Non documenté")))
            st.caption(f"{row.get('sector', 'Secteur non précisé')} · {badge}")
            if source_url:
                st.link_button(source_name or "Source", source_url, width="stretch")
            st.divider()


def render_ecosystem_native(rows: pd.DataFrame, ticker: str, company_name: str) -> None:
    st.markdown("#### Chaîne de valeur lisible")
    intrants = _ecosystem_layer(rows, "Intrants")
    clients = _ecosystem_layer(rows, "Clients servis")
    secteurs = _ecosystem_layer(rows, "Secteurs impactés")

    c1, c2, c3, c4 = st.columns([1.15, 0.85, 1.15, 1.15])
    with c1:
        _render_ecosystem_card("1. Intrants / ressources", intrants, "Aucun intrant documenté pour ce titre.")
    with c2:
        with st.container(border=True):
            st.markdown("**2. Entreprise**")
            st.markdown(f"### {company_name}")
            st.caption(ticker)
            documented = int((rows.get("confidence", pd.Series(dtype=str)).astype(str) == "Documenté").sum())
            st.metric("Liens documentés", documented)
    with c3:
        _render_ecosystem_card("3. Clients / usages servis", clients, "Aucun client ou usage documenté pour ce titre.")
    with c4:
        _render_ecosystem_card("4. Secteurs impactés", secteurs, "Aucun secteur documenté pour ce titre.")

    sourced = rows[rows.get("source_url", pd.Series(dtype=str)).astype(str).str.strip() != ""].copy()
    if not sourced.empty:
        st.markdown("#### Sources publiques intégrées")
        source_cols = [col for col in ["layer", "relation", "entity", "confidence", "source_name", "source_url"] if col in sourced.columns]
        st.dataframe(
            sourced[source_cols].rename(columns={
                "layer": "Couche",
                "relation": "Relation",
                "entity": "Entité / usage",
                "confidence": "Confiance",
                "source_name": "Source",
                "source_url": "Lien source",
            }),
            hide_index=True,
            width="stretch",
            column_config={"Lien source": st.column_config.LinkColumn("Lien source")},
        )


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
    with load_timer("focus_history"):
        history = add_indicators(fetch_history(ticker, period, interval))
perf_caption("focus_history", threshold=2.0)
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
event_note = (
    f" · {len(markers)} événement(s) affiché(s)"
    if show_markers and markers
    else ""
)
st.caption(
    "Graphique technique automatique : chandeliers, volume, moyennes mobiles, "
    "EMA 20 et bandes de Bollinger lorsque les données sont disponibles"
    f"{event_note}."
)
if show_markers and not markers:
    st.info(
        "Aucun événement daté n'a été trouvé pour la période affichée. "
        "Essaie une période plus longue ou vérifie les actualités disponibles."
    )

st.plotly_chart(
    price_chart(
        history,
        ticker,
        DEFAULT_PLOTLY_OVERLAYS,
        markers=markers if show_markers else None,
        price_lines=price_lines,
    ),
    width="stretch",
    config=plotly_config(),
    key=f"focus_plotly_auto_{ticker}_{period}_{interval}_{len(markers)}_{show_markers}",
)

ownership_quick = {
    "held_percent_institutions": info.get("heldPercentInstitutions"),
    "held_percent_insiders": info.get("heldPercentInsiders"),
}
institution_share = safe_float(ownership_quick.get("held_percent_institutions"))
insider_share = safe_float(ownership_quick.get("held_percent_insiders"))
retail_estimated_share = estimate_retail_share(ownership_quick)
last_volume = safe_float(last.get("Volume"))
volume_avg20 = safe_float(history.get("Volume", pd.Series(dtype=float)).tail(20).mean())
flow_cols = st.columns(4)
flow_cols[0].metric("Volume séance", format_compact(last_volume))
flow_cols[1].metric("Flux dominant", volume_flow_label(last.get("Open"), last.get("Close")))
flow_cols[2].metric("Institutions", percent_text(institution_share))
flow_cols[3].metric("Retail estimé", percent_text(retail_estimated_share))
if not np.isnan(insider_share):
    st.caption(
        "Lecture actionnariale : "
        f"institutions {percent_text(institution_share)}, "
        f"initiés {percent_text(insider_share)}, "
        f"retail estimé {percent_text(retail_estimated_share)}. "
        "Le retail exact n'est pas publié en temps réel ; Anatole l'estime comme la part restante hors institutions et initiés."
    )
else:
    st.caption(
        "Lecture actionnariale : "
        f"institutions {percent_text(institution_share)} et retail estimé {percent_text(retail_estimated_share)}. "
        "Le retail exact n'est pas publié en temps réel ; Anatole affiche donc une estimation."
    )
st.caption(
    "Code couleur du volume : vert = entrée / pression acheteuse dominante, rouge = sortie / pression vendeuse dominante. "
    f"Volume relatif actuel : {ratio_text(last_volume / max(volume_avg20, 1.0)) if not np.isnan(last_volume) and not np.isnan(volume_avg20) else 'N/D'}."
)

section = st.segmented_control(
    "Section",
    ["Aperçu", "Trader Pro", "Écosystème", "Finances", "Actualités", "Données avancées", "Analyse"],
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
        "plus haut : SMA 20, SMA 50, SMA 200, EMA 20, volume, bandes de Bollinger "
        "et événements lorsque l'option est activée."
    )


elif section == "Trader Pro":
    st.subheader("Trader Pro — Edge Lab")
    st.caption(
        "Un poste de décision tactique : lecture multi-horizon, confluence, setups, niveaux, taille de position, exécution et journal de trade. "
        "L'objectif est d'imposer une méthode froide, pas de promettre un résultat."
    )

    trader_dashboard = build_trader_dashboard(history, info, currency)
    top_controls = st.columns([1.2, 1.2, 2.2])
    with top_controls[0]:
        trader_style = st.segmented_control(
            "Horizon",
            ["Court terme", "Swing", "Position"],
            default="Swing",
            selection_mode="single",
            help="Ajuste la distance d'invalidation indicative selon l'horizon de travail.",
            key=f"focus_trader_style_{ticker}",
        )
    with top_controls[1]:
        decision_mode = st.segmented_control(
            "Mode",
            ["Diagnostic", "Plan", "Exécution"],
            default="Plan",
            selection_mode="single",
            key=f"focus_trader_decision_mode_{ticker}",
        )
    with top_controls[2]:
        st.caption(
            "Chaque chiffre est indicatif et doit être vérifié avec le carnet d'ordres, les nouvelles, la liquidité et ton propre risque. "
            "Anatole structure la décision; il ne remplace pas le jugement."
        )

    plan = trade_plan(history, currency=currency, style=trader_style or "Swing")
    score = trader_dashboard.get("score", 0)
    regime = trader_dashboard.get("regime", "N/D")
    bias = trader_dashboard.get("bias", "N/D")
    metrics_map = trader_dashboard.get("metrics", {}) or {}

    st.markdown("#### Cockpit tactique")
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Score trader", f"{score}/100")
    t2.metric("Régime", str(regime))
    t3.metric("Biais", str(bias))
    t4.metric("Volume relatif", metrics_map.get("Volume relatif", "N/D"))
    t5.metric("ATR 14", metrics_map.get("ATR 14", "N/D"), metrics_map.get("ATR %", None))

    t6, t7, t8, t9 = st.columns(4)
    t6.metric("Volatilité 20j", metrics_map.get("Volatilité 20j ann.", "N/D"))
    t7.metric("Support proche", metrics_map.get("Support proche", "N/D"))
    t8.metric("Résistance proche", metrics_map.get("Résistance proche", "N/D"))
    t9.metric("Drawdown période", metrics_map.get("Drawdown max", "N/D"))

    for line in trader_narrative(str(name), ticker, trader_dashboard, plan):
        st.write(line)

    overview_tab, setup_tab, risk_tab, execution_tab, journal_tab = st.tabs(
        ["Vue institutionnelle", "Setup", "Risque & taille", "Exécution", "Journal & assistant"]
    )

    with overview_tab:
        st.markdown("#### Alignement multi-horizon")
        timeframes = timeframe_alignment_table(history)
        if timeframes.empty:
            st.info("Historique insuffisant pour calculer l'alignement multi-horizon.")
        else:
            st.dataframe(timeframes, hide_index=True, width="stretch")

        st.markdown("#### Carte de confluence")
        confluence = confluence_map(history)
        if confluence.empty:
            st.info("Confluence indisponible pour ce titre.")
        else:
            st.dataframe(confluence, hide_index=True, width="stretch")

        st.markdown("#### Mémo institutionnel")
        st.text_area(
            "Lecture structurée",
            institutional_trade_memo(str(name), ticker, trader_dashboard, plan),
            height=310,
            key=f"focus_institutional_memo_{ticker}",
        )

    with setup_tab:
        st.markdown("#### Setups détectables")
        setups = setup_scorecards(history, plan)
        if setups.empty:
            st.info("Aucun setup exploitable calculé avec les données actuelles.")
        else:
            st.dataframe(
                setups,
                hide_index=True,
                width="stretch",
                column_config={
                    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                },
            )
            best_setup = str(setups.iloc[0].get("Setup", "N/D")) if not setups.empty else "N/D"
            best_score = int(setups.iloc[0].get("Score", 0)) if not setups.empty else 0
            st.success(f"Setup prioritaire à vérifier : {best_setup} · qualité indicative {best_score}/100")

        st.markdown("#### Niveaux de marché et zones de décision")
        levels = trader_levels_table(history, currency=currency)
        if levels.empty:
            st.info("Niveaux indisponibles pour ce titre sur la période affichée.")
        else:
            st.dataframe(levels, hide_index=True, width="stretch")

    with risk_tab:
        st.markdown("#### Plan de risque")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Entrée indicative", format_money(plan.get("entry"), currency))
        r2.metric("Invalidation", format_money(plan.get("stop"), currency))
        r3.metric("Risque / action", format_money(plan.get("risk_per_share"), currency))
        r4.metric("Cible 1", format_money(plan.get("target1"), currency), f"R/R {ratio_text(plan.get('rr1'))}")

        account_cols = st.columns([1, 1, 2])
        with account_cols[0]:
            account_size = st.number_input(
                "Capital simulé",
                min_value=500.0,
                max_value=5_000_000.0,
                value=float(st.session_state.get("focus_trader_capital", 10_000.0)),
                step=500.0,
                key=f"focus_trader_account_{ticker}",
            )
            st.session_state.focus_trader_capital = account_size
        with account_cols[1]:
            risk_pct = st.number_input(
                "Risque par idée (%)",
                min_value=0.1,
                max_value=10.0,
                value=float(st.session_state.get("focus_trader_risk_pct", 1.0)),
                step=0.1,
                key=f"focus_trader_risk_{ticker}",
            )
            st.session_state.focus_trader_risk_pct = risk_pct
        with account_cols[2]:
            st.caption(
                "La taille est calculée à partir du risque maximal choisi et de l'écart entre le prix et l'invalidation. "
                "Elle ne tient pas compte des frais, spreads, taxes, glissement ou contraintes personnelles."
            )

        sizing = position_sizing_table(plan, float(account_size), float(risk_pct))
        st.dataframe(sizing, hide_index=True, width="stretch")

        st.markdown("#### Matrice rendement / risque")
        st.dataframe(risk_reward_matrix(plan), hide_index=True, width="stretch")

    with execution_tab:
        st.markdown("#### Ladder d'exécution")
        st.dataframe(execution_ladder(plan), hide_index=True, width="stretch")

        st.markdown("#### Scénarios de prix")
        st.dataframe(scenario_table(plan), hide_index=True, width="stretch")

        st.markdown("#### Alertes intelligentes à créer")
        alerts = smart_alert_recipes(ticker, plan, trader_dashboard)
        st.dataframe(alerts, hide_index=True, width="stretch")

        st.markdown("#### Règles d'exécution")
        st.write("- Ne pas entrer parce que le titre bouge; entrer seulement si le plan défini se déclenche.")
        st.write("- Ne jamais augmenter la taille si l'invalidation devient plus éloignée.")
        st.write("- Si le prix atteint la cible 1, considérer une action : réduire, sécuriser, ou laisser courir avec stop remonté.")
        st.write("- Si le volume contredit la cassure, traiter le signal comme fragile.")
        st.write("- Si l'asymétrie R/R devient mauvaise, attendre le prochain setup.")

    with journal_tab:
        st.markdown("#### Journal de trade")
        journal = trader_journal_template(str(name), ticker, trader_dashboard, plan)
        st.text_area(
            "Modèle à copier dans ton journal",
            journal,
            height=310,
            key=f"focus_trader_journal_{ticker}",
        )

        st.markdown("#### Question avancée à l'assistant")
        assistant_prompt = (
            f"Analyse {ticker} comme un desk trader institutionnel. Utilise le régime {regime}, "
            f"le score trader {score}/100, le prix {format_money(plan.get('entry'), currency)}, "
            f"l'invalidation {format_money(plan.get('stop'), currency)}, la cible 1 {format_money(plan.get('target1'), currency)}, "
            f"les setups détectables, la confluence multi-horizon, le risque de faux signal, la taille de position, "
            f"et conclus avec un plan d'exécution conditionnel en 3 scénarios."
        )
        st.text_area(
            "Copier-coller dans l'assistant Anatole",
            assistant_prompt,
            height=180,
            key=f"focus_trader_prompt_{ticker}",
        )
        if st.button("Ouvrir l'assistant", width="stretch", key=f"focus_open_assistant_{ticker}"):
            st.session_state["assistant_prefill"] = assistant_prompt
            st.page_link("screens/13_Assistant.py", label="Aller à l'assistant", width="stretch")

    st.warning(
        "Rappel : Trader Pro fournit un cadre de lecture, de discipline et de gestion du risque. "
        "Il ne prédit pas le marché, ne garantit aucun résultat et ne constitue pas une recommandation personnalisée."
    )

elif section == "Écosystème":
    st.subheader("Écosystème du titre")
    st.caption(
        "Cette section cartographie les intrants, acteurs économiques et secteurs qui gravitent autour du titre. "
        "Elle est informative : elle ne prétend pas lister tous les contrats, fournisseurs ou clients réels."
    )

    ecosystem_rows, coverage = ecosystem_for_ticker(
        ticker=ticker,
        company_name=str(name),
        sector=str(info.get("sector") or fallback_sector),
        industry=str(info.get("industry") or ""),
    )
    metrics_map = ecosystem_metrics(ecosystem_rows)
    eco_cols = st.columns(4)
    eco_cols[0].metric("Intrants", metrics_map.get("intrants", 0))
    eco_cols[1].metric("Clients / usages", metrics_map.get("clients", 0))
    eco_cols[2].metric("Secteurs impactés", metrics_map.get("secteurs", 0))
    eco_cols[3].metric("Couverture", coverage)

    for line in ecosystem_explainer(ecosystem_rows, str(name), coverage):
        st.write(f"- {line}")

    documented_count = int((ecosystem_rows.get("confidence", pd.Series(dtype=str)).astype(str) == "Documenté").sum())
    if documented_count:
        st.success(f"{documented_count} lien(s) documenté(s) avec source affichés pour ce titre.")
    else:
        st.info("Aucune source précise n'est encore intégrée pour ce titre; Anatole affiche une lecture indicative par secteur.")

    render_ecosystem_native(ecosystem_rows, ticker, str(name))

    with st.expander("Vue réseau expérimentale", expanded=False):
        st.caption(
            "Cette vue réseau est conservée comme complément visuel. "
            "La chaîne de valeur lisible ci-dessus est prioritaire, car elle reste plus nette sur mobile et desktop."
        )
        st.plotly_chart(
            ecosystem_sankey(ecosystem_rows, ticker, str(name)),
            width="stretch",
            config=plotly_config(),
            key=f"ecosystem_sankey_{ticker}",
        )

    tab_chain, tab_affiliates, tab_sector = st.tabs(
        ["Chaîne de valeur", "Acteurs affiliés", "Contribution sectorielle"]
    )
    with tab_chain:
        chain = affiliation_table(ecosystem_rows)
        st.dataframe(chain, hide_index=True, width="stretch")
        st.caption(
            "Chaîne de lecture : Intrants → entreprise sélectionnée → clients/usages → secteurs impactés. "
            "La colonne Confiance distingue les éléments documentés localement des lectures indicatives."
        )
    with tab_affiliates:
        affiliates = affiliation_table(
            ecosystem_rows[ecosystem_rows["layer"].isin(["Intrants", "Clients servis"])]
        )
        if affiliates.empty:
            st.info("Aucun acteur affilié n'est encore documenté pour ce titre.")
        else:
            st.dataframe(affiliates, hide_index=True, width="stretch")
    with tab_sector:
        contribution = contribution_table(ecosystem_rows)
        if contribution.empty:
            st.info("Aucune contribution sectorielle n'est encore documentée pour ce titre.")
        else:
            st.dataframe(contribution, hide_index=True, width="stretch")

    st.warning(
        "À vérifier avant décision : cette carte d'écosystème est une aide à la compréhension, "
        "pas une recommandation d'investissement ni une preuve contractuelle."
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

st.divider()
show_strategy_lab = st.toggle(
    "Afficher le laboratoire de stratégies",
    value=False,
    help="Lance le backtest et les graphiques de stratégie seulement lorsque tu veux les consulter.",
    key=f"focus_strategy_lab_{ticker}",
)
if show_strategy_lab:
    st.subheader("Laboratoire de stratégies")

    st.caption(
        "Teste des stratégies classiques sur le titre affiché. "
        "Les résultats sont des simulations éducatives, pas des recommandations personnalisées."
    )

    with st.expander("Catalogue des 10 stratégies disponibles", expanded=False):
        st.dataframe(strategy_catalog_frame(), width="stretch", hide_index=True)

    strategy_keys = strategy_options()
    selected_strategy = st.selectbox(
        "Stratégie à tester",
        strategy_keys,
        index=0,
        format_func=lambda key: STRATEGIES[key].name,
        help="Les stratégies sont adaptées au backtest d'un titre individuel avec les données disponibles.",
        key=f"focus_strategy_select_{ticker}",
    )

    cost_bps = st.slider(
        "Coût de transaction estimé par changement d'exposition, en points de base",
        min_value=0,
        max_value=50,
        value=5,
        step=1,
        help="5 bps = 0,05 %. Cette valeur est indicative et ne tient pas compte de tous les coûts réels.",
        key=f"focus_strategy_cost_{ticker}",
    )

    strategy = STRATEGIES[selected_strategy]
    st.info(
        f"**{strategy.name}** · {strategy.family} — {strategy.description} "
        f"Données requises : {strategy.requirement}"
    )

    backtest = run_strategy_backtest(
        history,
        selected_strategy,
        transaction_cost_bps=float(cost_bps),
        initial_capital=10_000.0,
    )

    metrics = backtest.get("metrics", {})
    if not metrics:
        st.warning(
            "Historique insuffisant pour tester cette stratégie sur le titre et la période sélectionnés. "
            "Essaie une période plus longue."
        )
    else:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Rendement stratégie", f"{metrics.get('Rendement total', 0):+.1f}%")
        k2.metric("Buy & Hold", f"{metrics.get('Buy & Hold', 0):+.1f}%")
        k3.metric("CAGR", f"{metrics.get('CAGR', 0):+.1f}%")
        k4.metric("Drawdown max", f"{metrics.get('Drawdown max', 0):+.1f}%")

        k5, k6, k7, k8 = st.columns(4)
        k5.metric("Volatilité annualisée", f"{metrics.get('Volatilité annualisée', 0):.1f}%")
        sharpe_value = metrics.get("Sharpe indicatif")
        k6.metric(
            "Sharpe indicatif",
            "N/D" if pd.isna(sharpe_value) else f"{sharpe_value:.2f}",
        )
        k7.metric("Temps investi", f"{metrics.get('Temps investi', 0):.0f}%")
        k8.metric("Transactions", f"{int(metrics.get('Transactions', 0))}")

        st.plotly_chart(
            strategy_equity_chart(backtest, ticker),
            width="stretch",
            key=f"strategy_equity_{ticker}_{selected_strategy}_{period}_{interval}_{cost_bps}",
        )

        st.plotly_chart(
            strategy_signal_overlay(history, backtest, ticker),
            width="stretch",
            key=f"strategy_signals_{ticker}_{selected_strategy}_{period}_{interval}_{cost_bps}",
        )

        signals = backtest.get("signals")
        if isinstance(signals, pd.DataFrame) and not signals.empty:
            st.caption("Derniers signaux générés par la stratégie")
            signal_view = signals.tail(12).reset_index().rename(columns={"index": "Date"})
            keep_cols = [col for col in ["Date", "Type", "Close", "Signal", "Exposition"] if col in signal_view.columns]
            st.dataframe(signal_view[keep_cols], width="stretch", hide_index=True)
        else:
            st.caption("Aucun signal d'entrée ou de sortie détecté sur la période sélectionnée.")

    st.caption(
        "Limites : les backtests utilisent des données historiques, un modèle de coûts simplifié "
        "et n'incluent pas les impôts, l'écart acheteur-vendeur, les délais d'exécution ni les contraintes personnelles."
    )
else:
    st.caption("Laboratoire de stratégies désactivé pour accélérer l'ouverture de la fiche action.")