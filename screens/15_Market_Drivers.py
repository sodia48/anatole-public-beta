from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from core.analytics import market_pulse
from core.runtime import load_market_bundle
from core.ui import (
    apply_style,
    configure_page,
    footer,
    page_header,
    sidebar_context,
)


configure_page("Moteurs du marché", "🧭")
apply_style()
sidebar_context()
page_header(
    "Pourquoi le marché bouge ?",
    (
        "Clique sur un secteur pour identifier les actions qui ont le plus "
        "contribué à son mouvement."
    ),
    "🧭",
)

with st.spinner("Calcul des contributions du marché..."):
    constituents, _, market, features = load_market_bundle()

if features.empty:
    st.error("Données insuffisantes.")
    footer()
    st.stop()

work = features.copy()
work["PoidsIndice"] = pd.to_numeric(
    work.get("PoidsIndice"),
    errors="coerce",
).fillna(0)
work["Variation"] = pd.to_numeric(
    work.get("Variation"),
    errors="coerce",
)
work["ContributionPoints"] = (
    work["PoidsIndice"] * work["Variation"] / 100
)
work["ContributionAbsolue"] = work["ContributionPoints"].abs()
pulse = market_pulse(work)

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Mouvement pondéré indicatif",
    f"{pulse.get('weighted_change', np.nan):+.2f}%",
)
m2.metric(
    "Meilleur secteur",
    pulse.get("best_sector", "N/D"),
    f"{pulse.get('best_sector_change', np.nan):+.2f}%",
)
m3.metric(
    "Secteur le plus faible",
    pulse.get("worst_sector", "N/D"),
    f"{pulse.get('worst_sector_change', np.nan):+.2f}%",
)
m4.metric(
    "Ratio hausses / baisses",
    f"{pulse.get('advancers', 0)} / {pulse.get('decliners', 0)}",
)

sector = (
    work.groupby("Secteur", as_index=False)
    .agg(
        ContributionPoints=("ContributionPoints", "sum"),
        VariationMoyenne=("Variation", "mean"),
        Poids=("PoidsIndice", "sum"),
        NombreTitres=("Ticker", "count"),
    )
    .sort_values("ContributionPoints")
)

fig = px.bar(
    sector,
    x="ContributionPoints",
    y="Secteur",
    orientation="h",
    color="ContributionPoints",
    color_continuous_scale=["#DC2626", "#315A7D", "#059669"],
    color_continuous_midpoint=0,
    custom_data=[
        "Secteur",
        "VariationMoyenne",
        "Poids",
        "NombreTitres",
    ],
    title="Contribution sectorielle indicative au mouvement",
    labels={
        "ContributionPoints": "Contribution (points de % indicatifs)",
    },
)
fig.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "Contribution : %{x:+.3f} point<br>"
        "Variation moyenne : %{customdata[1]:+.2f}%<br>"
        "Poids total : %{customdata[2]:.2f}%<br>"
        "Titres : %{customdata[3]}<extra></extra>"
    ),
    selected={
        "marker": {
            "opacity": 1,
            "line": {"color": "#0F172A", "width": 2},
        }
    },
    unselected={"marker": {"opacity": 0.55}},
)
fig.update_layout(
    height=520,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(255,255,255,.55)",
    clickmode="event+select",
    margin={"l": 10, "r": 10, "t": 70, "b": 20},
)

st.caption(
    "Clique sur une barre pour afficher les principales actions "
    "qui expliquent la contribution du secteur."
)

chart_event = st.plotly_chart(
    fig,
    width="stretch",
    key="market_drivers_contribution_interactive",
    on_select="rerun",
    selection_mode="points",
    config={
        "displayModeBar": False,
        "scrollZoom": False,
        "responsive": True,
    },
)

selected_points = []
try:
    selected_points = list(chart_event.selection.points)
except (AttributeError, TypeError):
    try:
        selected_points = list(
            chart_event.get("selection", {}).get("points", [])
        )
    except (AttributeError, TypeError):
        selected_points = []

if selected_points:
    point = selected_points[0]
    clicked_sector = (
        point.get("y")
        or (
            point.get("customdata", [None])[0]
            if point.get("customdata")
            else None
        )
    )
    if clicked_sector in sector["Secteur"].tolist():
        st.session_state["selected_market_driver_sector"] = clicked_sector

available_sectors = sector["Secteur"].tolist()
selected_sector = st.session_state.get(
    "selected_market_driver_sector",
)

if selected_sector not in available_sectors:
    if not sector.empty:
        selected_sector = sector.loc[
            sector["ContributionPoints"].abs().idxmax(),
            "Secteur",
        ]
        st.session_state[
            "selected_market_driver_sector"
        ] = selected_sector

if selected_sector:
    sector_row = sector.loc[
        sector["Secteur"] == selected_sector
    ].iloc[0]
    sector_stocks = (
        work.loc[work["Secteur"] == selected_sector]
        .dropna(subset=["ContributionPoints"])
        .sort_values("ContributionAbsolue", ascending=False)
        .copy()
    )

    st.markdown(f"## Détail du secteur : {selected_sector}")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric(
        "Contribution du secteur",
        f"{sector_row['ContributionPoints']:+.3f} pt",
    )
    d2.metric(
        "Variation moyenne",
        f"{sector_row['VariationMoyenne']:+.2f}%",
    )
    d3.metric(
        "Poids indicatif",
        f"{sector_row['Poids']:.2f}%",
    )
    d4.metric(
        "Titres analysés",
        int(sector_row["NombreTitres"]),
    )

    top_sector_stocks = (
        sector_stocks.head(12)
        .sort_values("ContributionPoints")
    )

    stock_fig = px.bar(
        top_sector_stocks,
        x="ContributionPoints",
        y="Ticker",
        orientation="h",
        color="ContributionPoints",
        color_continuous_scale=[
            "#DC2626",
            "#315A7D",
            "#059669",
        ],
        color_continuous_midpoint=0,
        custom_data=[
            "Nom",
            "Variation",
            "PoidsIndice",
            "Secteur",
        ],
        title=(
            f"Actions principales derrière le mouvement de {selected_sector}"
        ),
        labels={
            "ContributionPoints": "Contribution indicative (point de %)",
            "Ticker": "Action",
        },
    )
    stock_fig.update_traces(
        hovertemplate=(
            "<b>%{y} — %{customdata[0]}</b><br>"
            "Variation : %{customdata[1]:+.2f}%<br>"
            "Poids : %{customdata[2]:.2f}%<br>"
            "Contribution : %{x:+.3f} point"
            "<extra></extra>"
        )
    )
    stock_fig.update_layout(
        height=max(360, 42 * len(top_sector_stocks) + 120),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.55)",
        showlegend=False,
        margin={"l": 10, "r": 10, "t": 70, "b": 20},
    )
    st.plotly_chart(
        stock_fig,
        width="stretch",
        key=f"market_driver_stocks_{selected_sector}",
        config={"displayModeBar": False, "responsive": True},
    )

    positive_sector = (
        sector_stocks.loc[
            sector_stocks["ContributionPoints"] > 0,
            [
                "Ticker",
                "Nom",
                "Variation",
                "PoidsIndice",
                "ContributionPoints",
            ],
        ]
        .sort_values("ContributionPoints", ascending=False)
        .head(8)
    )
    negative_sector = (
        sector_stocks.loc[
            sector_stocks["ContributionPoints"] < 0,
            [
                "Ticker",
                "Nom",
                "Variation",
                "PoidsIndice",
                "ContributionPoints",
            ],
        ]
        .sort_values("ContributionPoints")
        .head(8)
    )

    detail_left, detail_right = st.columns(2)
    with detail_left:
        st.subheader("Actions qui soutiennent le secteur")
        if positive_sector.empty:
            st.info("Aucune contribution positive significative.")
        else:
            st.dataframe(
                positive_sector,
                hide_index=True,
                width="stretch",
                column_config={
                    "Variation": st.column_config.NumberColumn(
                        format="%+.2f%%"
                    ),
                    "PoidsIndice": st.column_config.NumberColumn(
                        "Poids",
                        format="%.2f%%",
                    ),
                    "ContributionPoints": (
                        st.column_config.NumberColumn(
                            "Contribution",
                            format="%+.3f",
                        )
                    ),
                },
            )

    with detail_right:
        st.subheader("Actions qui freinent le secteur")
        if negative_sector.empty:
            st.info("Aucune contribution négative significative.")
        else:
            st.dataframe(
                negative_sector,
                hide_index=True,
                width="stretch",
                column_config={
                    "Variation": st.column_config.NumberColumn(
                        format="%+.2f%%"
                    ),
                    "PoidsIndice": st.column_config.NumberColumn(
                        "Poids",
                        format="%.2f%%",
                    ),
                    "ContributionPoints": (
                        st.column_config.NumberColumn(
                            "Contribution",
                            format="%+.3f",
                        )
                    ),
                },
            )

st.divider()

left, right = st.columns(2)
with left:
    st.subheader("Principaux moteurs positifs du TSX 60")
    positive = work.nlargest(
        12,
        "ContributionPoints",
    )[
        [
            "Ticker",
            "Nom",
            "Secteur",
            "Variation",
            "PoidsIndice",
            "ContributionPoints",
        ]
    ]
    st.dataframe(
        positive,
        hide_index=True,
        width="stretch",
        column_config={
            "Variation": st.column_config.NumberColumn(
                format="%+.2f%%"
            ),
            "PoidsIndice": st.column_config.NumberColumn(
                format="%.2f%%"
            ),
            "ContributionPoints": st.column_config.NumberColumn(
                format="%+.3f"
            ),
        },
    )

with right:
    st.subheader("Principaux freins du TSX 60")
    negative = work.nsmallest(
        12,
        "ContributionPoints",
    )[
        [
            "Ticker",
            "Nom",
            "Secteur",
            "Variation",
            "PoidsIndice",
            "ContributionPoints",
        ]
    ]
    st.dataframe(
        negative,
        hide_index=True,
        width="stretch",
        column_config={
            "Variation": st.column_config.NumberColumn(
                format="%+.2f%%"
            ),
            "PoidsIndice": st.column_config.NumberColumn(
                format="%.2f%%"
            ),
            "ContributionPoints": st.column_config.NumberColumn(
                format="%+.3f"
            ),
        },
    )

st.warning(
    "Cette décomposition est une approximation fondée sur les poids "
    "disponibles et les variations observées. Elle n'établit pas une "
    "causalité économique certaine."
)
footer()
