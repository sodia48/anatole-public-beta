from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from core.analytics import market_pulse
from core.universe import current_universe
from core.runtime import load_light_market_bundle
from core.device import mobile_is_lite, mobile_chart_height
from core.ui import (
    apply_style,
    configure_page,
    footer,
    page_header,
    sidebar_context,
    plotly_mobile_config,
)


def _fmt_pct(value: object) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "N/D"


def _fmt_pt(value: object) -> str:
    try:
        return f"{float(value):+.3f} pt"
    except Exception:
        return "N/D"


def render_mobile_contributor_cards(frame: pd.DataFrame, limit: int = 10) -> None:
    """Liste mobile lisible des principaux contributeurs."""
    if frame.empty:
        st.info("Aucune action disponible pour ce secteur.")
        return
    top = frame.head(limit).copy()
    for i, row in top.iterrows():
        contribution = float(row.get("ContributionPoints", 0) or 0)
        icon = "▲" if contribution >= 0 else "▼"
        tone = "Soutien" if contribution >= 0 else "Frein"
        with st.container(border=True):
            left, right = st.columns([0.58, 0.42], vertical_alignment="center")
            with left:
                st.markdown(f"**{icon} {row.get('Ticker', 'N/D')} — {row.get('Nom', '')}**")
                st.caption(str(row.get("Secteur", "")))
            with right:
                st.metric(tone, _fmt_pt(row.get("ContributionPoints")), _fmt_pct(row.get("Variation")))
            yahoo = str(row.get("YahooTicker", row.get("Ticker", "")))
            if st.button("Ouvrir la fiche", key=f"market_driver_mobile_focus_{yahoo}_{i}", width="stretch"):
                st.session_state.selected_ticker = yahoo
                st.switch_page("screens/14_Focus.py")


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
        "Sélectionne un secteur pour voir les actions qui expliquent le plus "
        "son mouvement, sans carte instable ni zoom involontaire."
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

selection_col, chart_col = st.columns([0.9, 1.55], gap="large")

with selection_col:
    with st.container(border=True):
        st.markdown("### Secteur à analyser")
        manual_sector = st.selectbox(
            "Choisir un secteur",
            available_sectors,
            index=(
                available_sectors.index(selected_sector)
                if selected_sector in available_sectors
                else 0
            ),
            key="market_driver_sector_selector_v577",
        )
        if manual_sector != selected_sector:
            st.session_state["selected_market_driver_sector"] = manual_sector
            selected_sector = manual_sector
            sector_row = sector.loc[sector["Secteur"] == selected_sector].iloc[0]
            sector_stocks = (
                work.loc[work["Secteur"] == selected_sector]
                .dropna(subset=["ContributionPoints"])
                .sort_values("ContributionAbsolue", ascending=False)
                .copy()
            )

        if sector_row is not None:
            st.markdown(f"## {selected_sector}")
            s1, s2 = st.columns(2)
            s1.metric("Contribution", _fmt_pt(sector_row.get("ContributionPoints")))
            s2.metric("Variation", _fmt_pct(sector_row.get("VariationMoyenne")))
            s3, s4 = st.columns(2)
            s3.metric("Poids indicatif", f"{float(sector_row.get('Poids', 0) or 0):.2f}%")
            s4.metric("Titres", int(sector_row.get("NombreTitres", 0) or 0))
            st.caption("Lecture indicative fondée sur les poids disponibles et les variations observées.")

with chart_col:
    fig = px.bar(
        sector,
        x="ContributionPoints",
        y="Secteur",
        orientation="h",
        color="ContributionPoints",
        color_continuous_scale=["#DC2626", "#315A7D", "#059669"],
        color_continuous_midpoint=0,
        custom_data=["Secteur", "VariationMoyenne", "Poids", "NombreTitres"],
        title="Contribution sectorielle indicative",
        labels={"ContributionPoints": "Contribution (points de % indicatifs)"},
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
        height=mobile_chart_height(520, 390),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.55)",
        margin={"l": 8, "r": 8, "t": 60, "b": 18},
        coloraxis_colorbar={"title": "Contribution", "thickness": 12},
        showlegend=False,
    )
    st.plotly_chart(
        fig,
        width="stretch",
        key="market_drivers_sector_static_v577",
        config=plotly_mobile_config(),
    )
    st.caption("Graphique stabilisé : la sélection se fait avec le menu à gauche pour éviter les zooms involontaires.")

with st.container(border=True):
    st.markdown("### Principaux moteurs du secteur")
    if sector_stocks.empty:
        st.info("Aucune action disponible pour ce secteur.")
    elif mobile_is_lite():
        render_mobile_contributor_cards(sector_stocks, limit=8)
    else:
        preview = sector_stocks.head(8).copy()
        display = preview[["Ticker", "Nom", "Variation", "PoidsIndice", "ContributionPoints"]].copy()
        st.dataframe(
            display,
            hide_index=True,
            width="stretch",
            column_config={
                "Variation": st.column_config.NumberColumn("Variation", format="%+.2f%%"),
                "PoidsIndice": st.column_config.NumberColumn("Poids", format="%.2f%%"),
                "ContributionPoints": st.column_config.NumberColumn("Contribution", format="%+.3f pt"),
            },
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
        height=max(360, 38 * len(top_sector_stocks) + 110),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.55)",
        showlegend=False,
        margin={"l": 8, "r": 8, "t": 58, "b": 18},
    )
    if mobile_is_lite():
        render_mobile_contributor_cards(sector_stocks.head(12), limit=12)
    else:
        st.plotly_chart(
            stock_fig,
            width="stretch",
            key=f"market_driver_stocks_{selected_sector}_v577",
            config=plotly_mobile_config(),
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
