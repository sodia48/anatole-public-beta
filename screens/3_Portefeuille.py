from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.analytics import portfolio_risk_metrics, portfolio_table
from core.charts import equity_curve_chart, portfolio_allocation_chart
from core.data import fetch_batch_history, fetch_market_snapshot, load_constituents
from core.database import get_positions, replace_positions
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.utils import format_money, normalise_symbol

configure_page("Portefeuille", "💼")
apply_style()
profile = sidebar_context()
page_header(
    "Portefeuille virtuel",
    "Enregistre tes positions, calcule les gains, l'allocation, la volatilité, le Sharpe et le drawdown.",
    "💼",
)

constituents, diagnostics = load_constituents()
positions = get_positions(profile)
editable = positions[["ticker", "quantity", "average_cost", "notes"]].copy() if not positions.empty else pd.DataFrame(
    [{"ticker": "RY.TO", "quantity": 10.0, "average_cost": 0.0, "notes": ""}]
)

st.subheader("Positions")
editor = st.data_editor(
    editable,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    column_config={
        "ticker": st.column_config.TextColumn("Ticker", required=True),
        "quantity": st.column_config.NumberColumn("Quantité", min_value=-1_000_000.0, step=1.0, required=True),
        "average_cost": st.column_config.NumberColumn("Coût moyen", min_value=0.0, step=0.01, format="$%.2f", required=True),
        "notes": st.column_config.TextColumn("Notes"),
    },
)

if st.button("💾 Enregistrer le portefeuille", type="primary"):
    cleaned = editor.copy()
    cleaned["ticker"] = cleaned["ticker"].apply(lambda value: normalise_symbol(value, constituents))
    replace_positions(profile, cleaned)
    st.success("Portefeuille enregistré dans SQLite.")
    st.rerun()

positions = get_positions(profile)
if positions.empty:
    st.info("Ajoute puis enregistre au moins une position.")
    footer()
    st.stop()

position_tickers = tuple(sorted(positions["ticker"].str.upper().unique().tolist()))
with st.spinner("Mise à jour des cotations et du risque..."):
    quotes = fetch_market_snapshot(position_tickers)
    history_tickers = tuple(sorted(set(position_tickers) | {"XIU.TO"}))
    histories = fetch_batch_history(history_tickers, "2y", "1d")
portfolio = portfolio_table(positions, quotes, constituents)

if portfolio.empty:
    st.warning("Impossible de calculer le portefeuille.")
    footer()
    st.stop()

total_value = portfolio["Valeur"].sum(skipna=True)
total_cost = portfolio["Coût total"].sum(skipna=True)
total_pnl = portfolio["Gain/perte $"].sum(skipna=True)
daily_pnl = (portfolio["Valeur"] * portfolio["Variation jour %"] / 100).sum(skipna=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Valeur actuelle", format_money(total_value))
m2.metric("Coût total", format_money(total_cost))
m3.metric("Gain/perte", format_money(total_pnl), f"{(total_pnl / total_cost * 100):+.2f}%" if total_cost else None)
m4.metric("Variation estimée du jour", format_money(daily_pnl))

st.dataframe(
    portfolio,
    hide_index=True,
    width="stretch",
    column_config={
        "Coût moyen": st.column_config.NumberColumn(format="$%.2f"),
        "Prix": st.column_config.NumberColumn(format="$%.2f"),
        "Valeur": st.column_config.NumberColumn(format="$%.2f"),
        "Coût total": st.column_config.NumberColumn(format="$%.2f"),
        "Gain/perte $": st.column_config.NumberColumn(format="$%+.2f"),
        "Gain/perte %": st.column_config.NumberColumn(format="%+.2f%%"),
        "Variation jour %": st.column_config.NumberColumn(format="%+.2f%%"),
        "Poids %": st.column_config.NumberColumn(format="%.2f%%"),
    },
)

allocation_col1, allocation_col2 = st.columns(2)
with allocation_col1:
    st.plotly_chart(portfolio_allocation_chart(portfolio, "Ticker"), width="stretch", key="portefeuille_allocation_ticker")
with allocation_col2:
    st.plotly_chart(portfolio_allocation_chart(portfolio, "Secteur"), width="stretch", key="portefeuille_allocation_secteur")

risk_free = st.number_input("Taux sans risque annuel (%)", min_value=0.0, max_value=20.0, value=3.0, step=0.25) / 100
risk = portfolio_risk_metrics(portfolio, histories, risk_free)
if risk:
    st.subheader("Risque du portefeuille")
    r1, r2, r3, r4, r5, r6 = st.columns(6)
    r1.metric("Rendement annualisé", f"{risk['annual_return']:+.2f}%")
    r2.metric("Volatilité annualisée", f"{risk['annual_volatility']:.2f}%")
    r3.metric("Ratio de Sharpe", f"{risk['sharpe']:.2f}")
    r4.metric("Bêta vs XIU", f"{risk['beta']:.2f}" if not np.isnan(risk['beta']) else "N/D")
    r5.metric("Drawdown maximal", f"{risk['max_drawdown']:.2f}%")
    r6.metric("VaR 95 % quotidienne", f"{risk['var95_daily']:.2f}%")
    curve = pd.DataFrame({"Equity": risk["equity_curve"] * total_value})
    st.plotly_chart(equity_curve_chart(curve, "Évolution historique estimée du portefeuille"), width="stretch", key="portefeuille_equity_curve")
    st.subheader("Contribution de chaque position au risque")
    st.dataframe(
        risk["risk_contribution"].sort_values("Contribution au risque %", ascending=False),
        hide_index=True,
        width="stretch",
        column_config={
            "Poids %": st.column_config.NumberColumn(format="%.2f%%"),
            "Contribution au risque %": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

st.download_button(
    "Télécharger le portefeuille en CSV",
    portfolio.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"portefeuille_{profile}.csv",
    mime="text/csv",
)

footer()
