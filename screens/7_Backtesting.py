from __future__ import annotations

import pandas as pd
import streamlit as st

from core.analytics import run_backtest
from core.charts import equity_curve_chart
from core.config import BACKTEST_STRATEGIES
from core.data import fetch_history, load_constituents
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context

configure_page("Backtesting", "🧪")
apply_style()
profile = sidebar_context()
page_header(
    "Backtesting de stratégies",
    "Teste des règles simples avec frais de transaction et signaux décalés pour limiter le biais d'anticipation.",
    "🧪",
)

constituents, diagnostics = load_constituents()
lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))

c1, c2, c3 = st.columns(3)
with c1:
    ticker = st.selectbox(
        "Titre",
        constituents["YahooTicker"].tolist(),
        format_func=lambda value: lookup.get(value, value),
    )
with c2:
    strategy_label = st.selectbox("Stratégie", list(BACKTEST_STRATEGIES))
with c3:
    period = st.selectbox("Historique", ["1y", "2y", "5y", "10y", "max"], index=2)

p1, p2, p3, p4 = st.columns(4)
with p1:
    initial_capital = st.number_input("Capital initial", min_value=100.0, value=10_000.0, step=500.0)
with p2:
    fee_bps = st.number_input("Frais par transaction (points de base)", min_value=0.0, value=5.0, step=1.0)
with p3:
    rsi_buy = st.number_input("RSI d'achat", min_value=1.0, max_value=50.0, value=30.0, disabled=BACKTEST_STRATEGIES[strategy_label] != "rsi")
with p4:
    rsi_sell = st.number_input("RSI de vente", min_value=50.0, max_value=99.0, value=70.0, disabled=BACKTEST_STRATEGIES[strategy_label] != "rsi")

with st.spinner("Calcul du backtest..."):
    history = fetch_history(ticker, period, "1d")
    result = run_backtest(
        history,
        strategy=BACKTEST_STRATEGIES[strategy_label],
        initial_capital=initial_capital,
        fee_bps=fee_bps,
        rsi_buy=rsi_buy,
        rsi_sell=rsi_sell,
    )

if result.frame.empty:
    st.error("Données insuffisantes pour cette combinaison.")
    footer()
    st.stop()

metrics = result.metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Rendement total", f"{metrics['Rendement total (%)']:+.2f}%")
m2.metric("Rendement annualisé", f"{metrics['Rendement annualisé (%)']:+.2f}%")
m3.metric("Volatilité", f"{metrics['Volatilité annualisée (%)']:.2f}%")
m4.metric("Sharpe", f"{metrics['Sharpe']:.2f}")

m5, m6, m7, m8 = st.columns(4)
m5.metric("Drawdown max", f"{metrics['Drawdown max (%)']:.2f}%")
m6.metric("Transactions", int(metrics["Transactions"]))
m7.metric("Taux de réussite", f"{metrics['Taux de réussite (%)']:.1f}%" if pd.notna(metrics["Taux de réussite (%)"]) else "N/D")
m8.metric("Valeur finale", f"${metrics['Valeur finale']:,.2f}")

st.plotly_chart(equity_curve_chart(result.frame, f"{ticker} · {strategy_label}"), width="stretch", key=f"backtesting_equity_{ticker}_{strategy_label}")

st.subheader("Transactions clôturées")
if result.trades.empty:
    st.caption("Aucune transaction clôturée sur la période.")
else:
    st.dataframe(
        result.trades,
        hide_index=True,
        width="stretch",
        column_config={
            "Prix entrée": st.column_config.NumberColumn(format="$%.2f"),
            "Prix sortie": st.column_config.NumberColumn(format="$%.2f"),
            "Rendement %": st.column_config.NumberColumn(format="%+.2f%%"),
        },
    )

st.warning(
    "Un backtest historique ne garantit aucun rendement futur. Les résultats ne modélisent pas entièrement les écarts de prix, la liquidité, les impôts ni les contraintes d'exécution."
)

footer()
