from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from core.config import TORONTO_TZ
from core.ipo_calendar import load_upcoming_ipos
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("IPO à venir", "🚀")
apply_style()
sidebar_context()
page_header(
    "IPO à venir",
    "Radar des introductions en bourse : dates annoncées, dossiers déposés, nouvelles inscriptions et sources consolidées.",
    "🚀",
    show_universe_selector=False,
)

st.caption(
    "Anatole consolide plusieurs sources publiques et fusionne les doublons détectés. "
    "Les IPO peuvent être modifiées, reportées ou annulées : cette page sert au suivi informatif des événements de marché, "
    "pas à une recommandation d'achat."
)

today = pd.Timestamp.now(tz=TORONTO_TZ).date()



def _public_source_label(name: object) -> str:
    value = str(name or "").strip()
    replacements = {
        "Fichier local": "Catalogue interne",
        "Finnhub": "Source premium",
        "Financial Modeling Prep": "Source premium",
        "SEC EDGAR": "Dépôts réglementaires",
    }
    return replacements.get(value, value)


def _clean_source_text(value: object) -> str:
    parts = [part.strip() for part in str(value or "").split("+") if part.strip()]
    cleaned = [_public_source_label(part) for part in parts]
    return " + ".join(dict.fromkeys(cleaned)) if cleaned else "—"


def _clean_status_text(status: object) -> str:
    text = str(status or "").strip()
    lowered = text.lower()
    if text.startswith("OK"):
        return text.replace("OK", "Disponible", 1)
    if "clé absente" in lowered:
        return "Disponible sur abonnement"
    if "non configur" in lowered:
        return "Catalogue standard"
    if "indisponible" in lowered or "erreur" in lowered or "http" in lowered or "importerror" in lowered:
        return "Temporairement indisponible"
    return text or "À vérifier"


def _clean_statuses(statuses: dict) -> dict[str, str]:
    return {_public_source_label(source): _clean_status_text(status) for source, status in statuses.items()}

control_1, control_2, control_3, control_4 = st.columns([1.0, 1.1, 1.2, 1.7])
with control_1:
    horizon_label = st.selectbox(
        "Horizon calendrier",
        ["30 jours", "90 jours", "180 jours", "365 jours"],
        index=2,
    )
with control_2:
    dataset_mode = st.selectbox(
        "Vue",
        ["Tout", "Calendrier IPO", "Pipeline", "Canada", "États-Unis"],
        index=0,
    )
with control_3:
    min_confidence = st.selectbox(
        "Confiance minimale",
        ["Toutes", "Indicative", "Moyenne", "Élevée"],
        index=0,
    )
with control_4:
    query = st.text_input(
        "Recherche",
        placeholder="Nom, symbole, bourse, pays, source...",
    ).strip()

horizon_days = int(horizon_label.split()[0])
start = today.isoformat()
end = (today + timedelta(days=horizon_days)).isoformat()

refresh_col, hint_col = st.columns([1, 3])
with refresh_col:
    if st.button("Actualiser le radar IPO", width="stretch"):
        load_upcoming_ipos.clear()
        st.rerun()
with hint_col:
    st.caption(
        "Le pipeline inclut des dossiers S-1/F-1, des filings IPO et des nouvelles inscriptions. "
        "Une ligne peut donc être une IPO datée ou une société à surveiller avant date officielle."
    )

with st.spinner("Chargement du radar IPO..."):
    ipos, statuses = load_upcoming_ipos(start, end)

public_statuses = _clean_statuses(statuses)

work = ipos.copy()
if not work.empty:
    work["DateParsed"] = pd.to_datetime(work.get("Date", pd.Series(dtype=str)), errors="coerce")
    for column in [
        "Société",
        "Symbole",
        "Bourse",
        "Pays",
        "Type d’événement",
        "Statut",
        "Source",
        "Confiance donnée",
        "Maturité IPO",
    ]:
        if column not in work.columns:
            work[column] = ""

    if "Source" in work.columns:
        work["Source"] = work["Source"].map(_clean_source_text)

    if dataset_mode == "Calendrier IPO":
        work = work.loc[work["Type d’événement"].astype(str).str.contains("Calendrier", case=False, na=False)].copy()
    elif dataset_mode == "Pipeline":
        work = work.loc[
            work["Type d’événement"].astype(str).str.contains("Dépôt|depot|filing|réglementaire|reglementaire|Nouvelle", case=False, regex=True, na=False)
        ].copy()
    elif dataset_mode == "Canada":
        work = work.loc[work["Pays"].astype(str).str.contains("Canada", case=False, na=False)].copy()
    elif dataset_mode == "États-Unis":
        work = work.loc[work["Pays"].astype(str).str.contains("États|Etats|United|US", case=False, regex=True, na=False)].copy()

    confidence_order = {"Indicative": 1, "Moyenne": 2, "Élevée": 3}
    if min_confidence != "Toutes":
        required = confidence_order.get(min_confidence, 1)
        work = work.loc[
            work["Confiance donnée"].map(lambda value: confidence_order.get(str(value), 0) >= required)
        ].copy()

    available_exchanges = sorted(
        exchange
        for exchange in work.get("Bourse", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
        if exchange
    )
    available_maturities = sorted(
        maturity
        for maturity in work.get("Maturité IPO", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
        if maturity
    )

    filter_1, filter_2 = st.columns(2)
    with filter_1:
        selected_exchanges = st.multiselect(
            "Bourses",
            available_exchanges,
            default=available_exchanges,
        )
    with filter_2:
        selected_maturities = st.multiselect(
            "Maturité",
            available_maturities,
            default=available_maturities,
        )

    if selected_exchanges:
        work = work.loc[work["Bourse"].isin(selected_exchanges)].copy()
    if selected_maturities:
        work = work.loc[work["Maturité IPO"].isin(selected_maturities)].copy()

    if query:
        searchable_columns = [
            "Société",
            "Symbole",
            "Bourse",
            "Pays",
            "Type d’événement",
            "Statut",
            "Source",
            "Confiance donnée",
        ]
        haystack = (
            work[[column for column in searchable_columns if column in work.columns]]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
        )
        work = work.loc[haystack.str.contains(query.lower(), regex=False)].copy()

count = len(work)
calendar_mask = (
    work.get("Type d’événement", pd.Series(dtype=str)).astype(str).str.contains("Calendrier", case=False, na=False)
    if count
    else pd.Series(dtype=bool)
)
pipeline_mask = ~calendar_mask if count else pd.Series(dtype=bool)

next_date = "N/D"
if count and "DateParsed" in work.columns:
    dated_calendar = work.loc[calendar_mask & work["DateParsed"].notna()].sort_values("DateParsed")
    if not dated_calendar.empty:
        next_date = dated_calendar.iloc[0]["Date"]

metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
metric_1.metric("IPO suivies", count)
metric_2.metric("Calendrier daté", int(calendar_mask.sum()) if count else 0)
metric_3.metric("Pipeline", int(pipeline_mask.sum()) if count else 0)
metric_4.metric("Prochaine date", next_date)
metric_5.metric("Sources actives", sum(1 for status in public_statuses.values() if str(status).startswith("Disponible")))

available_sources = [name for name, status in public_statuses.items() if str(status).startswith("Disponible")]
st.caption(
    "Sources disponibles : " + (", ".join(available_sources[:6]) if available_sources else "couverture limitée pour le moment")
)

public_ok = [name for name, status in public_statuses.items() if str(status).startswith("Disponible")]
if count <= 2 and len(public_ok) <= 1:
    st.info(
        "La couverture publique est limitée pour le moment. Anatole affiche les éléments détectés, "
        "mais certaines IPO peuvent ne pas encore apparaître dans le radar."
    )

if work.empty:
    st.info(
        "Aucune IPO à afficher avec les sources actuellement disponibles et les filtres sélectionnés. "
        "Élargis l'horizon ou repasse la vue à “Tout”."
    )
    with st.expander("Comment améliorer la couverture"):
        st.markdown(
            """
            Pour une meilleure lecture du marché primaire, Anatole combine les calendriers publics, les nouvelles inscriptions et les dépôts réglementaires disponibles.

            La couverture peut varier selon les sources, la date et les règles d’accès des fournisseurs. Les sociétés sans date officielle restent dans le pipeline lorsqu’elles sont détectées.
            """
        )
    footer()
    st.stop()

# Préparation des onglets.
calendar_work = work.loc[calendar_mask].copy() if count else work.copy()
pipeline_work = work.loc[pipeline_mask].copy() if count else work.copy()
radar_work = work.sort_values(
    ["Score donnée", "Sources détectées", "DateParsed"],
    ascending=[False, False, True],
    na_position="last",
).copy()

tab_radar, tab_calendar, tab_pipeline, tab_sources = st.tabs(
    ["Radar", "Calendrier", "Pipeline", "Sources"]
)

with tab_radar:
    st.markdown("#### Radar IPO")
    st.caption(
        "Le score donnée ne mesure pas la qualité de l’investissement. Il mesure seulement la robustesse de l’information disponible : nombre de sources, date, symbole, prix ou montant."
    )

    top = radar_work.head(8).copy()
    if not top.empty:
        cards = st.columns(4)
        for idx, (_, row) in enumerate(top.iterrows()):
            with cards[idx % 4]:
                title = str(row.get("Société", "")).strip() or "Société à confirmer"
                symbol = str(row.get("Symbole", "")).strip() or "N/D"
                exchange = str(row.get("Bourse", "")).strip() or "N/D"
                date_value = str(row.get("Date", "")).strip() or "À confirmer"
                confidence = str(row.get("Confiance donnée", "Indicative"))
                score = row.get("Score donnée", 0)
                st.metric(f"{symbol} · {exchange}", f"{score}/100", confidence)
                st.caption(f"{title} · {date_value}")

    chart_col_1, chart_col_2 = st.columns(2)
    with chart_col_1:
        by_maturity = (
            work.assign(**{"Maturité IPO": work["Maturité IPO"].replace("", "N/D")})
            .groupby("Maturité IPO", as_index=False)
            .size()
            .rename(columns={"size": "Nombre"})
        )
        if not by_maturity.empty:
            fig = px.bar(
                by_maturity,
                x="Maturité IPO",
                y="Nombre",
                title="Maturité du pipeline",
                labels={"Nombre": "Nombre d’événements"},
            )
            fig.update_layout(height=340, margin={"l": 10, "r": 10, "t": 58, "b": 20})
            st.plotly_chart(fig, width="stretch")
    with chart_col_2:
        by_country = (
            work.assign(Pays=work["Pays"].replace("", "N/D"))
            .groupby("Pays", as_index=False)
            .size()
            .rename(columns={"size": "Nombre"})
        )
        if not by_country.empty:
            fig = px.bar(
                by_country,
                x="Pays",
                y="Nombre",
                title="Répartition géographique",
                labels={"Nombre": "Nombre d’événements"},
            )
            fig.update_layout(height=340, margin={"l": 10, "r": 10, "t": 58, "b": 20})
            st.plotly_chart(fig, width="stretch")

    st.markdown("#### Fiche rapide")
    choices = [
        f"{row.get('Société', '')} · {row.get('Symbole', 'N/D')} · {row.get('Date', 'À confirmer')}"
        for _, row in radar_work.iterrows()
    ]
    if choices:
        selected = st.selectbox("Sélectionner une société", choices)
        selected_index = choices.index(selected)
        selected_row = radar_work.iloc[selected_index]
        detail_1, detail_2, detail_3 = st.columns(3)
        detail_1.metric("Confiance donnée", str(selected_row.get("Confiance donnée", "N/D")), f"{selected_row.get('Score donnée', 0)}/100")
        detail_2.metric("Sources détectées", int(selected_row.get("Sources détectées", 1)))
        detail_3.metric("Maturité", str(selected_row.get("Maturité IPO", "N/D")))
        st.write(
            f"**{selected_row.get('Société', 'Société à confirmer')}** — "
            f"symbole **{selected_row.get('Symbole', 'N/D') or 'N/D'}**, "
            f"bourse **{selected_row.get('Bourse', 'N/D') or 'N/D'}**, "
            f"date **{selected_row.get('Date', 'À confirmer')}**."
        )
        st.caption(f"Points à vérifier : {selected_row.get('Points à vérifier', 'N/D')}")
        link = str(selected_row.get("Lien", "")).strip()
        if link.startswith("http"):
            st.link_button("Ouvrir la source", link)

with tab_calendar:
    st.markdown("#### Calendrier des IPO datées")
    if calendar_work.empty:
        st.info("Aucune IPO datée dans les filtres actuels. Consulte l’onglet Pipeline pour les dossiers déposés ou les inscriptions récentes.")
    else:
        chart_data = (
            calendar_work.assign(Bourse=calendar_work["Bourse"].replace("", "N/D"))
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
                title="Calendrier IPO par bourse",
                labels={"Nombre": "Nombre d'IPO"},
            )
            fig.update_layout(height=360, margin={"l": 10, "r": 10, "t": 58, "b": 20})
            st.plotly_chart(fig, width="stretch")
        st.dataframe(
            calendar_work[[column for column in [
                "Date", "Jours avant IPO", "Moment", "Société", "Symbole", "Bourse", "Pays", "Prix indicatif", "Actions offertes", "Montant estimé", "Maturité IPO", "Confiance donnée", "Sources détectées", "Source", "Lien"
            ] if column in calendar_work.columns]],
            hide_index=True,
            width="stretch",
            column_config={
                "Jours avant IPO": st.column_config.NumberColumn(format="%d"),
                "Lien": st.column_config.LinkColumn("Lien"),
            },
        )

with tab_pipeline:
    st.markdown("#### Pipeline pré-IPO et nouvelles inscriptions")
    st.caption(
        "Cette vue ajoute les sociétés qui ont déposé un dossier IPO ou qui apparaissent dans des nouvelles inscriptions publiques. "
        "Elles ne disposent pas toujours d’une date d’IPO officielle."
    )
    if pipeline_work.empty:
        st.info("Aucune ligne pipeline dans les filtres actuels.")
    else:
        st.dataframe(
            pipeline_work[[column for column in [
                "Date", "Moment", "Société", "Symbole", "Bourse", "Pays", "Type d’événement", "Statut", "Maturité IPO", "Confiance donnée", "Sources détectées", "Points à vérifier", "Source", "Lien"
            ] if column in pipeline_work.columns]],
            hide_index=True,
            width="stretch",
            column_config={"Lien": st.column_config.LinkColumn("Lien")},
        )

with tab_sources:
    st.markdown("#### État des sources")
    status_table = pd.DataFrame(
        [{"Source": source, "État": status} for source, status in public_statuses.items()]
    )
    st.dataframe(status_table, hide_index=True, width="stretch")

    st.markdown("#### Couverture par source détectée")
    source_rows = []
    for _, row in work.iterrows():
        for source in str(row.get("Source", "")).split("+"):
            source = source.strip()
            if source:
                source_rows.append({"Source": source, "Société": row.get("Société", "")})
    if source_rows:
        source_counts = pd.DataFrame(source_rows).groupby("Source", as_index=False).size().rename(columns={"size": "Lignes uniques"})
        st.dataframe(source_counts.sort_values("Lignes uniques", ascending=False), hide_index=True, width="stretch")

visible_columns = [
    "Date",
    "Jours avant IPO",
    "Moment",
    "Société",
    "Symbole",
    "Bourse",
    "Pays",
    "Type d’événement",
    "Prix indicatif",
    "Actions offertes",
    "Montant estimé",
    "Statut",
    "Maturité IPO",
    "Confiance donnée",
    "Sources détectées",
    "Score donnée",
    "Points à vérifier",
    "Source",
    "Lien",
]
visible_columns = [column for column in visible_columns if column in work.columns]

csv = work[visible_columns].to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "Télécharger le radar IPO",
    csv,
    file_name=f"ipo_radar_{today.isoformat()}.csv",
    mime="text/csv",
)

footer()
