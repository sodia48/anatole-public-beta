from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from core.config import TORONTO_TZ
from core.ipo_calendar import load_upcoming_ipos, source_summary
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("IPO à venir", "🚀")
apply_style()
sidebar_context()
page_header(
    "IPO à venir",
    "Suivez les sociétés qui préparent leur entrée en bourse et repérez les prochaines fenêtres de cotation.",
    "🚀",
)

st.caption(
    "Les données IPO peuvent être modifiées, reportées ou annulées. "
    "Cette page sert au suivi informatif des événements de marché, pas à une recommandation d'achat."
)

today = pd.Timestamp.now(tz=TORONTO_TZ).date()

control_1, control_2, control_3 = st.columns([1.1, 1.2, 1.7])
with control_1:
    horizon_label = st.selectbox(
        "Horizon",
        ["30 jours", "90 jours", "180 jours", "365 jours"],
        index=2,
    )
with control_2:
    include_tbc = st.checkbox("Inclure les dates à confirmer", value=True)
with control_3:
    query = st.text_input(
        "Recherche",
        placeholder="Nom, symbole, bourse, statut...",
    ).strip()

horizon_days = int(horizon_label.split()[0])
start = today.isoformat()
end = (today + timedelta(days=horizon_days)).isoformat()

if st.button("Actualiser le calendrier", width="stretch"):
    load_upcoming_ipos.clear()
    st.rerun()

with st.spinner("Chargement du calendrier IPO..."):
    ipos, statuses = load_upcoming_ipos(start, end)

if not ipos.empty:
    work = ipos.copy()
    work["DateParsed"] = pd.to_datetime(work["Date"], errors="coerce")

    if not include_tbc:
        work = work.loc[work["DateParsed"].notna()].copy()

    available_exchanges = sorted(
        exchange
        for exchange in work.get("Bourse", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
        if exchange
    )
    available_statuses = sorted(
        status
        for status in work.get("Statut", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
        if status
    )

    filter_1, filter_2 = st.columns(2)
    with filter_1:
        selected_exchanges = st.multiselect(
            "Bourses",
            available_exchanges,
            default=available_exchanges,
        )
    with filter_2:
        selected_statuses = st.multiselect(
            "Statuts",
            available_statuses,
            default=available_statuses,
        )

    if selected_exchanges:
        work = work.loc[work["Bourse"].isin(selected_exchanges)].copy()
    if selected_statuses:
        work = work.loc[work["Statut"].isin(selected_statuses)].copy()

    if query:
        haystack = (
            work[["Société", "Symbole", "Bourse", "Statut", "Source"]]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
        )
        work = work.loc[haystack.str.contains(query.lower(), regex=False)].copy()
else:
    work = ipos.copy()

count = len(work)
next_date = "N/D"
if count and "DateParsed" in work.columns:
    dated = work.loc[work["DateParsed"].notna()].sort_values("DateParsed")
    if not dated.empty:
        next_date = dated.iloc[0]["Date"]

metric_1, metric_2, metric_3, metric_4 = st.columns(4)
metric_1.metric("IPO suivies", count)
metric_2.metric("Prochaine date", next_date)
metric_3.metric(
    "Bourses couvertes",
    len(work["Bourse"].dropna().replace("", pd.NA).dropna().unique()) if count and "Bourse" in work else 0,
)
metric_4.metric(
    "Sources actives",
    sum(1 for status in statuses.values() if status == "OK"),
)

st.caption(source_summary(statuses))

if work.empty:
    st.info(
        "Aucune IPO à afficher avec les sources actuellement connectées et les filtres sélectionnés. "
        "Ajoutez une source IPO ou élargissez l'horizon de recherche."
    )
    with st.expander("Configurer une source IPO"):
        st.markdown(
            """
            Options supportées :

            - Ajouter `FINNHUB_API_KEY` dans les secrets Streamlit ou les variables d'environnement.
            - Ajouter `FMP_API_KEY` dans les secrets Streamlit ou les variables d'environnement.
            - Déposer un fichier `data/ipo_calendar.csv` avec les colonnes `Date`, `Société`, `Symbole`, `Bourse`, `Prix indicatif`, `Actions offertes`, `Statut`, `Lien`.

            Le fichier local est pratique si tu veux garder une liste vérifiée manuellement pour la bêta publique.
            """
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Date": "2026-08-15",
                        "Société": "Exemple Technologies",
                        "Symbole": "EXPL",
                        "Bourse": "NASDAQ",
                        "Prix indicatif": "$18-$22",
                        "Actions offertes": "10 000 000",
                        "Statut": "À venir",
                        "Lien": "",
                    }
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    footer()
    st.stop()

# Graphique simple pour repérer où se concentre le pipeline IPO.
chart_data = (
    work.assign(Bourse=work["Bourse"].replace("", "N/D"))
    .groupby(["Bourse", "Moment"], as_index=False)
    .size()
    .rename(columns={"size": "Nombre"})
)
if not chart_data.empty:
    fig = px.bar(
        chart_data,
        x="Bourse",
        y="Nombre",
        color="Moment",
        title="Pipeline IPO par bourse",
        labels={"Nombre": "Nombre d'IPO"},
    )
    fig.update_layout(
        height=360,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.55)",
        margin={"l": 10, "r": 10, "t": 58, "b": 20},
    )
    st.plotly_chart(fig, width="stretch")

st.markdown("#### Calendrier")
visible_columns = [
    "Date",
    "Jours avant IPO",
    "Moment",
    "Société",
    "Symbole",
    "Bourse",
    "Prix indicatif",
    "Actions offertes",
    "Statut",
    "Source",
    "Lien",
]
visible_columns = [column for column in visible_columns if column in work.columns]

display = work[visible_columns].copy()
st.dataframe(
    display,
    hide_index=True,
    width="stretch",
    column_config={
        "Jours avant IPO": st.column_config.NumberColumn(format="%d"),
        "Lien": st.column_config.LinkColumn("Lien"),
    },
)

csv = display.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Télécharger le calendrier IPO",
    csv,
    file_name=f"ipo_calendar_{today.isoformat()}.csv",
    mime="text/csv",
)

with st.expander("État des sources"):
    status_table = pd.DataFrame(
        [{"Source": source, "État": status} for source, status in statuses.items()]
    )
    st.dataframe(status_table, hide_index=True, width="stretch")

footer()
