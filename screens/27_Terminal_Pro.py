from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from core.intelligence_engine import (
    build_institutional_brief,
    detect_dislocations,
    explain_ticker,
    institutional_watchlist,
    market_regime,
    prepare_market_frame,
    score_titles,
    search_tickers,
    sector_rotation,
)
from core.runtime import load_technical_bundle
from core.ui import apply_style, configure_page, footer, page_header, plotly_mobile_config, sidebar_context
from core.utils import format_money


configure_page("Terminal Pro", "💎")
apply_style()
profile = sidebar_context()
page_header(
    "Terminal Pro",
    "Un radar de marché premium pour transformer l’univers actif en signaux lisibles, scénarios et priorités d’analyse.",
)

st.caption(
    "Les scores servent à prioriser l’analyse. Ils ne constituent pas une recommandation personnalisée d’achat, de vente ou de conservation."
)

try:
    constituents, diagnostics, market, features = load_technical_bundle()
except Exception:
    constituents, diagnostics, market, features = pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame()

base = features if isinstance(features, pd.DataFrame) and not features.empty else market
universe_label = str(diagnostics.get("universe_label") or diagnostics.get("universe") or "Univers actif")
frame = prepare_market_frame(base)

if frame.empty:
    st.warning("Les données du marché ne sont pas disponibles pour le moment. Réessaie après le prochain rafraîchissement.")
    footer()
    st.stop()

scored = score_titles(frame)
regime = market_regime(frame)
sectors = sector_rotation(frame)
radar = institutional_watchlist(frame, limit=20)
dislocations = detect_dislocations(frame, limit=30)


def _fmt_pct(value: object, decimals: int = 2, signed: bool = True) -> str:
    try:
        number = float(value)
        if pd.isna(number):
            return "N/D"
        prefix = "+" if signed and number > 0 else ""
        return f"{prefix}{number:.{decimals}f} %".replace(".", ",")
    except Exception:
        return "N/D"


def _fmt_num(value: object, decimals: int = 1) -> str:
    try:
        number = float(value)
        if pd.isna(number):
            return "N/D"
        return f"{number:,.{decimals}f}".replace(",", " ").replace(".", ",")
    except Exception:
        return "N/D"


def _stock_actions(row: pd.Series, key_prefix: str) -> None:
    ticker = str(row.get("Ticker", "")).strip()
    yahoo = str(row.get("YahooTicker", ticker)).strip()
    if not ticker:
        return
    st.session_state["anatole_bridge_ticker"] = ticker
    st.session_state["anatole_bridge_yahoo"] = yahoo
    st.session_state["selected_ticker"] = yahoo
    st.session_state["focus_ticker"] = yahoo
    st.session_state["screener_symbol_query"] = ticker
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Focus", key=f"{key_prefix}_{ticker}_focus", width="stretch"):
            st.switch_page("screens/14_Focus.py")
    with c2:
        if st.button("Screener", key=f"{key_prefix}_{ticker}_screener", width="stretch"):
            st.switch_page("screens/1_Screener.py")
    with c3:
        if st.button("Insiders", key=f"{key_prefix}_{ticker}_insiders", width="stretch"):
            st.switch_page("screens/25_Insiders.py")
    with c4:
        if st.button("Alerte", key=f"{key_prefix}_{ticker}_alert", width="stretch"):
            st.switch_page("screens/4_Alertes.py")


m1, m2, m3, m4 = st.columns(4)
m1.metric("Régime", regime.label)
m2.metric("Largeur", _fmt_pct(regime.breadth * 100 if pd.notna(regime.breadth) else None, 1, signed=False))
m3.metric("Mouvement pondéré", _fmt_pct(regime.weighted_change))
m4.metric("Risque", regime.risk_level)
st.caption(f"{universe_label} · {regime.advancers} titres en hausse · {regime.decliners} en baisse · Secteur fort : {regime.top_sector} · Secteur faible : {regime.bottom_sector}")

tabs = st.tabs([
    "Brief exécutif",
    "Radar titres",
    "Dislocations",
    "Rotation sectorielle",
    "Recherche pro",
    "Méthode",
])

with tabs[0]:
    left, right = st.columns([1.25, 1])
    with left:
        st.subheader("Lecture de marché")
        st.markdown(build_institutional_brief(frame))
    with right:
        st.subheader("Score Anatole — Top profils")
        top_display = radar[[c for c in ["Ticker", "Secteur", "Score Anatole", "Catégorie", "Risque principal"] if c in radar.columns]].head(8)
        st.dataframe(
            top_display,
            hide_index=True,
            width="stretch",
            column_config={
                "Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            },
        )
        if not sectors.empty:
            fig = px.bar(
                sectors.sort_values("Variation moyenne", ascending=True),
                x="Variation moyenne",
                y="Secteur",
                orientation="h",
                title="Rotation sectorielle",
                text="Variation moyenne",
            )
            fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside", cliponaxis=False)
            fig.update_layout(height=360, margin={"l": 8, "r": 8, "t": 42, "b": 8})
            st.plotly_chart(fig, width="stretch", config=plotly_mobile_config())

with tabs[1]:
    st.subheader("Radar titres institutionnel")
    st.caption("Classement explicable construit à partir du momentum, de la technique, du risque, de la valorisation, du revenu et de la liquidité.")
    sector_filter = st.selectbox(
        "Filtrer par secteur",
        ["Tous"] + sorted(scored["Secteur"].dropna().astype(str).unique().tolist()),
        key="terminal_sector_filter",
    )
    category_filter = st.selectbox(
        "Filtrer par catégorie",
        ["Toutes"] + sorted(scored["Catégorie"].dropna().astype(str).unique().tolist()),
        key="terminal_category_filter",
    )
    table = scored.copy()
    if sector_filter != "Tous":
        table = table[table["Secteur"].astype(str) == sector_filter]
    if category_filter != "Toutes":
        table = table[table["Catégorie"].astype(str) == category_filter]
    cols = [
        "Ticker",
        "Nom",
        "Secteur",
        "Prix",
        "Variation",
        "Score Anatole",
        "Catégorie",
        "Lecture Anatole",
        "Risque principal",
        "Points à vérifier",
    ]
    st.dataframe(
        table[[c for c in cols if c in table.columns]].head(80),
        hide_index=True,
        width="stretch",
        column_config={
            "Prix": st.column_config.NumberColumn(format="$%.2f"),
            "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
            "Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        },
    )
    if not table.empty:
        selected = st.selectbox(
            "Ouvrir un titre du radar",
            table["Ticker"].head(80).tolist(),
            index=None,
            placeholder="Choisir un titre…",
            key="terminal_open_stock",
        )
        if selected:
            row = table.loc[table["Ticker"] == selected].iloc[0]
            st.markdown(explain_ticker(frame, selected))
            _stock_actions(row, "terminal_radar")

with tabs[2]:
    st.subheader("Dislocations et mouvements atypiques")
    st.caption("Repère les titres avec RSI extrême, volume inhabituel, forte variation ou pression technique. À vérifier, pas à acheter automatiquement.")
    cols = ["Ticker", "Nom", "Secteur", "Variation", "RSI14", "VolumeRelatif", "Score Anatole", "Catégorie", "Points à vérifier"]
    st.dataframe(
        dislocations[[c for c in cols if c in dislocations.columns]],
        hide_index=True,
        width="stretch",
        column_config={
            "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
            "RSI14": st.column_config.NumberColumn(format="%.1f"),
            "VolumeRelatif": st.column_config.NumberColumn(format="%.2fx"),
            "Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
        },
    )

with tabs[3]:
    st.subheader("Rotation sectorielle")
    if sectors.empty:
        st.info("La rotation sectorielle n’est pas disponible avec les données actuelles.")
    else:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.dataframe(
                sectors,
                hide_index=True,
                width="stretch",
                column_config={
                    "Variation moyenne": st.column_config.NumberColumn(format="%+.2f%%"),
                    "Largeur": st.column_config.NumberColumn(format="%.0f%%"),
                    "Poids": st.column_config.NumberColumn(format="%.2f"),
                    "Score rotation": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
                },
            )
        with c2:
            chosen_sector = st.selectbox("Analyser un secteur", sectors["Secteur"].tolist(), key="terminal_sector_detail")
            subset = scored[scored["Secteur"].astype(str) == str(chosen_sector)].sort_values("Score Anatole", ascending=False)
            st.markdown(f"### {chosen_sector}")
            if not subset.empty:
                st.write(f"Meilleur profil : **{subset.iloc[0]['Ticker']}** · score {_fmt_num(subset.iloc[0]['Score Anatole'], 1)}/100")
                st.write(f"À surveiller : **{subset.iloc[-1]['Ticker']}** · {subset.iloc[-1]['Risque principal']}")
                st.dataframe(
                    subset[["Ticker", "Variation", "Score Anatole", "Catégorie", "Risque principal"]].head(12),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
                        "Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
                    },
                )

with tabs[4]:
    st.subheader("Recherche pro")
    query = st.text_input(
        "Recherche par symbole, société, secteur ou catégorie",
        placeholder="Ex. RY, banques, énergie, leadership, pression technique…",
        key="terminal_pro_search",
    )
    if query:
        results = search_tickers(frame, query, limit=20)
        if results.empty:
            st.info("Aucune correspondance dans l’univers actif.")
        else:
            st.dataframe(
                results[["Ticker", "Nom", "Secteur", "Score Anatole", "Catégorie", "Risque principal"]],
                hide_index=True,
                width="stretch",
                column_config={"Score Anatole": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f")},
            )
            first = results.iloc[0]
            st.markdown(explain_ticker(frame, str(first["Ticker"])))
            _stock_actions(first, "terminal_search")

with tabs[5]:
    st.subheader("Méthode")
    st.markdown(
        """
### Ce que le Terminal Pro mesure

Le Terminal Pro ne prédit pas le marché. Il transforme les données disponibles dans Anatole en **priorités d’analyse**.

Le **Score Anatole** agrège six familles de signaux :

1. **Momentum** : variation récente, distance aux moyennes mobiles et rendements disponibles.
2. **Technique** : équilibre RSI, confirmation par le volume, structure autour des moyennes mobiles.
3. **Risque** : volatilité indicative, bêta et amplitude du mouvement de séance.
4. **Valorisation** : lecture relative du P/E lorsque disponible.
5. **Revenu** : rendement de dividende relatif lorsque disponible.
6. **Liquidité / poids** : capitalisation et poids indicatif dans l’univers actif.

### Pourquoi c’est puissant

- L’utilisateur ne regarde plus seulement un prix : il voit **pourquoi un titre ressort**.
- Les secteurs sont comparés avec la largeur de marché, pas seulement avec la performance moyenne.
- Les anomalies ne sont pas cachées : RSI extrême, volume inhabituel, pression de séance et risques sont explicités.

### Limites

- Les données peuvent être différées, partielles ou révisées.
- Les scores doivent être confirmés par les nouvelles, les états financiers et les dépôts officiels.
- Ce module ne donne pas de recommandation personnalisée.
"""
    )

footer()
