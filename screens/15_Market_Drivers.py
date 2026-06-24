from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_plotly_events2 import plotly_events

from core.analytics import market_pulse
from core.universe import current_universe
from core.runtime import load_light_market_bundle
from core.ui import (
    apply_style,
    configure_page,
    footer,
    page_header,
    sidebar_context,
)


def resolve_clicked_sector(
    clicked_points: list[dict],
    available_sectors: list[str],
) -> str | None:
    """Retourne le secteur associé au dernier clic Plotly."""
    if not clicked_points:
        return None

    point = clicked_points[-1]

    # Pour une barre horizontale Plotly, le nom du secteur est normalement
    # renvoyé directement dans la coordonnée y.
    y_value = point.get("y")
    if isinstance(y_value, str) and y_value in available_sectors:
        return y_value

    # Solution de secours selon la version du composant.
    for key in ("pointIndex", "pointNumber"):
        index = point.get(key)
        if isinstance(index, int) and 0 <= index < len(available_sectors):
            return available_sectors[index]

    return None


configure_page("Moteurs du marché", "🧭")
apply_style()
sidebar_context()
page_header(
    "Pourquoi le marché bouge ?",
    (
        "Clique sur un secteur pour afficher immédiatement les actions "
        "qui expliquent le plus son mouvement."
    ),
    "🧭",
)

with st.spinner("Calcul des contributions du marché..."):
    constituents, _, market = load_light_market_bundle()

if market.empty:
    st.error("Données insuffisantes.")
    footer()
    st.stop()

work = market.copy()
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
    .reset_index(drop=True)
)

available_sectors = sector["Secteur"].tolist()

selected_sector = st.session_state.get("selected_market_driver_sector")
if selected_sector not in available_sectors and not sector.empty:
    selected_sector = sector.loc[
        sector["ContributionPoints"].abs().idxmax(),
        "Secteur",
    ]
    st.session_state["selected_market_driver_sector"] = selected_sector

# Préparer les données du secteur avant le rendu afin que le panneau à droite
# soit toujours visible dès l'ouverture de la page.
sector_row = None
sector_stocks = pd.DataFrame()
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

chart_col, summary_col = st.columns([1.65, 1], gap="large")

with chart_col:
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
        title=(
            "Contribution sectorielle indicative au mouvement"
            + (
                f"<br><sup>Secteur sélectionné : {selected_sector}</sup>"
                if selected_sector
                else ""
            )
        ),
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
    )
    fig.update_layout(
        height=560,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.55)",
        margin={"l": 10, "r": 10, "t": 80, "b": 20},
        coloraxis_colorbar={
            "title": "Contribution",
            "thickness": 15,
        },
    )

    st.caption(
        "Clique directement sur une barre. Le panneau de droite sera "
        "mis à jour avec les actions contributrices."
    )

    clicked_points = plotly_events(
        fig,
        click_event=True,
        select_event=False,
        hover_event=False,
        override_height=560,
        override_width="100%",
        config={
            "displayModeBar": False,
            "scrollZoom": False,
            "displaylogo": False,
            "responsive": True,
        },
        key="market_drivers_sector_click_v469",
    )

clicked_sector = resolve_clicked_sector(
    clicked_points,
    available_sectors,
)

if clicked_sector and clicked_sector != selected_sector:
    st.session_state["selected_market_driver_sector"] = clicked_sector
    selected_sector = clicked_sector
    sector_row = sector.loc[
        sector["Secteur"] == selected_sector
    ].iloc[0]
    sector_stocks = (
        work.loc[work["Secteur"] == selected_sector]
        .dropna(subset=["ContributionPoints"])
        .sort_values("ContributionAbsolue", ascending=False)
        .copy()
    )

with summary_col:
    with st.container(border=True):
        st.markdown("### Actions contributrices")

        # Sélecteur de secours et moyen rapide de comparer les secteurs.
        manual_sector = st.selectbox(
            "Secteur affiché",
            available_sectors,
            index=(
                available_sectors.index(selected_sector)
                if selected_sector in available_sectors
                else 0
            ),
            key="market_driver_sector_fallback",
        )

        if manual_sector != selected_sector:
            st.session_state[
                "selected_market_driver_sector"
            ] = manual_sector
            selected_sector = manual_sector
            sector_row = sector.loc[
                sector["Secteur"] == selected_sector
            ].iloc[0]
            sector_stocks = (
                work.loc[work["Secteur"] == selected_sector]
                .dropna(subset=["ContributionPoints"])
                .sort_values("ContributionAbsolue", ascending=False)
                .copy()
            )

        if sector_row is not None:
            st.markdown(f"## {selected_sector}")

            s1, s2 = st.columns(2)
            s1.metric(
                "Contribution",
                f"{sector_row['ContributionPoints']:+.3f} pt",
            )
            s2.metric(
                "Variation moyenne",
                f"{sector_row['VariationMoyenne']:+.2f}%",
            )

            s3, s4 = st.columns(2)
            s3.metric(
                "Poids indicatif",
                f"{sector_row['Poids']:.2f}%",
            )
            s4.metric(
                "Titres",
                int(sector_row["NombreTitres"]),
            )

            st.markdown("#### Principaux moteurs")

            preview = sector_stocks.head(7).copy()
            if preview.empty:
                st.info("Aucune action disponible pour ce secteur.")
            else:
                for _, row in preview.iterrows():
                    contribution = float(row["ContributionPoints"])
                    variation = float(row["Variation"])
                    icon = "▲" if contribution >= 0 else "▼"

                    st.markdown(
                        f"**{icon} {row['Ticker']} — {row['Nom']}**  \n"
                        f"Variation : `{variation:+.2f}%` · "
                        f"Contribution : `{contribution:+.3f} pt`"
                    )

st.divider()

if selected_sector and sector_row is not None:
    st.markdown(f"## Analyse détaillée : {selected_sector}")

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
        height=max(380, 42 * len(top_sector_stocks) + 130),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.55)",
        showlegend=False,
        margin={"l": 10, "r": 10, "t": 70, "b": 20},
    )
    st.plotly_chart(
        stock_fig,
        width="stretch",
        key=f"market_driver_stocks_{selected_sector}_v469",
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
    st.subheader(f"Principaux moteurs positifs — {current_universe().short_label}")
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
    st.subheader(f"Principaux freins — {current_universe().short_label}")
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
