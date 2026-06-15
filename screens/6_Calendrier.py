from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core.data import fetch_calendar_bundle, load_constituents
from core.economic_events import (
    DEFAULT_COUNTRIES,
    fetch_official_economic_calendar,
    filter_economic_events,
    importance_counts,
    to_display_frame,
    upcoming_highlights,
)
from core.database import get_macro_events, get_watchlist, replace_macro_events
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context

configure_page("Calendrier", "🗓️")
apply_style()
profile = sidebar_context()
page_header(
    "Calendrier financier",
    "Centralise les événements économiques importants, les résultats, les dividendes et les dates clés.",
    "🗓️",
)


st.subheader("Événements économiques officiels et gratuits")

st.caption(
    "Sources sans clé API : Statistique Canada, Banque du Canada, "
    "BLS, BEA et calendrier du FOMC. Les heures sont affichées "
    "en heure de Toronto."
)

today_date = date.today()
default_start = today_date - timedelta(days=7)
default_end = today_date + timedelta(days=60)

date_col1, date_col2, importance_col = st.columns([1, 1, 1.2])
with date_col1:
    start_date = st.date_input(
        "Début",
        value=default_start,
        key="official_econ_start",
    )
with date_col2:
    end_date = st.date_input(
        "Fin",
        value=default_end,
        key="official_econ_end",
    )
with importance_col:
    min_importance = st.selectbox(
        "Importance minimale",
        ["Très élevée", "Élevée", "Moyenne", "Toutes"],
        index=1,
        key="official_econ_importance",
    )

source_col1, source_col2, source_col3 = st.columns(3)
with source_col1:
    include_statcan = st.checkbox(
        "Statistique Canada",
        value=True,
        key="source_statcan",
    )
    include_boc = st.checkbox(
        "Banque du Canada",
        value=True,
        key="source_boc",
    )
with source_col2:
    include_bls = st.checkbox(
        "USA : BLS (emploi et inflation)",
        value=True,
        key="source_bls",
    )
    include_bea = st.checkbox(
        "USA : BEA (PIB, PCE et commerce)",
        value=True,
        key="source_bea",
    )
with source_col3:
    include_fomc = st.checkbox(
        "USA : décisions du FOMC",
        value=True,
        key="source_fomc",
    )
    show_medium_events = st.checkbox(
        "Afficher aussi les événements moyens",
        value=False,
        key="show_medium_official_events",
    )

if show_medium_events and min_importance == "Élevée":
    effective_importance = "Moyenne"
else:
    effective_importance = min_importance

if start_date > end_date:
    st.error("La date de début doit être antérieure à la date de fin.")
    official_events = pd.DataFrame()
    source_statuses = {}
else:
    with st.spinner("Synchronisation des calendriers officiels..."):
        official_events, source_statuses = fetch_official_economic_calendar(
            start_date.isoformat(),
            end_date.isoformat(),
            include_statcan=include_statcan,
            include_boc=include_boc,
            include_bls=include_bls,
            include_bea=include_bea,
            include_fomc=include_fomc,
        )

if source_statuses:
    available_sources = sum(
        1 for status in source_statuses.values() if status == "OK"
    )
    total_sources = len(source_statuses)
    if available_sources == total_sources:
        st.caption(
            f"Sources officielles synchronisées : {available_sources}/{total_sources}."
        )
    else:
        st.caption(
            f"Calendrier consolidé à partir de {available_sources} source(s) "
            f"officielle(s) disponible(s) sur {total_sources}. "
            "Les sources momentanément bloquées sont ignorées automatiquement."
        )

if not official_events.empty:
    countries = sorted(
        official_events["Pays"].dropna().astype(str).unique().tolist()
    )
    categories = sorted(
        official_events["Catégorie"].dropna().astype(str).unique().tolist()
    )
    sources = sorted(
        official_events["Source"].dropna().astype(str).unique().tolist()
    )

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(
        [1.15, 1.15, 1.05, 1.25]
    )
    with filter_col1:
        selected_countries = st.multiselect(
            "Pays",
            countries,
            default=[
                country
                for country in DEFAULT_COUNTRIES
                if country in countries
            ],
            key="official_econ_countries",
        )
    with filter_col2:
        selected_categories = st.multiselect(
            "Catégories",
            categories,
            default=categories,
            key="official_econ_categories",
        )
    with filter_col3:
        selected_sources = st.multiselect(
            "Sources",
            sources,
            default=sources,
            key="official_econ_sources",
        )
    with filter_col4:
        economic_search = st.text_input(
            "Recherche",
            placeholder="CPI, taux, emploi, PIB, PCE...",
            key="official_econ_search",
        )

    filtered_economic = filter_economic_events(
        official_events,
        countries=selected_countries,
        categories=selected_categories,
        sources=selected_sources,
        min_importance=effective_importance,
        search=economic_search,
    )

    counts = importance_counts(filtered_economic)
    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Très élevée", counts["Très élevée"])
    metric2.metric("Élevée", counts["Élevée"])
    metric3.metric("Moyenne", counts["Moyenne"])
    metric4.metric("Total", len(filtered_economic))

    highlights = upcoming_highlights(filtered_economic, limit=8)
    if not highlights.empty:
        st.markdown("#### Prochains événements prioritaires")
        for _, event in highlights.iterrows():
            if event["Importance"] == "Très élevée":
                badge = "🔴"
            elif event["Importance"] == "Élevée":
                badge = "🟠"
            else:
                badge = "🟡"

            with st.container(border=True):
                main_col, importance_box = st.columns([4, 1])
                main_col.markdown(
                    f"**{badge} {event['Événement']}**  \n"
                    f"{event['Pays']} · {event['Source']} · "
                    f"{event['Date']} à {event['Heure']} ET"
                )
                if str(event.get("Description", "")).strip():
                    main_col.caption(event["Description"])
                importance_box.metric(
                    "Importance",
                    event["Importance"],
                )
                if str(event.get("Lien", "")).strip():
                    st.link_button(
                        "Consulter la source officielle",
                        event["Lien"],
                    )

    st.markdown("#### Calendrier économique consolidé")
    display_frame = to_display_frame(filtered_economic)
    st.dataframe(
        display_frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Date": st.column_config.TextColumn("Date", width="small"),
            "Heure": st.column_config.TextColumn("Heure ET", width="small"),
            "Importance": st.column_config.TextColumn(
                "Importance",
                width="small",
            ),
            "Pays": st.column_config.TextColumn("Pays", width="small"),
            "Devise": st.column_config.TextColumn("Devise", width="small"),
            "Catégorie": st.column_config.TextColumn(
                "Catégorie",
                width="medium",
            ),
            "Événement": st.column_config.TextColumn(
                "Événement",
                width="large",
            ),
            "Description": st.column_config.TextColumn(
                "Description",
                width="large",
            ),
            "Source": st.column_config.TextColumn("Source", width="medium"),
            "Lien": st.column_config.LinkColumn(
                "Source officielle",
                display_text="Ouvrir",
            ),
        },
    )

    st.download_button(
        "Télécharger le calendrier filtré",
        data=display_frame.to_csv(index=False).encode("utf-8"),
        file_name="anatole_calendrier_officiel.csv",
        mime="text/csv",
    )
else:
    st.info(
        "Aucun événement officiel n'a été trouvé pour cette période. "
        "Élargis la plage de dates ou vérifie l'état des sources."
    )

st.caption(
    "Statistique Canada publie généralement The Daily à 8 h 30 ET. "
    "La section américaine est volontairement limitée aux publications "
    "les plus importantes pour les marchés."
)

st.divider()

constituents, diagnostics = load_constituents()

lookup = dict(zip(constituents["YahooTicker"], constituents["Ticker"] + " — " + constituents["Nom"]))
watchlist = [ticker for ticker in get_watchlist(profile) if ticker in lookup]
selected = st.multiselect(
    "Titres du calendrier (maximum 10)",
    constituents["YahooTicker"].tolist(),
    default=(watchlist[:8] or constituents["YahooTicker"].head(5).tolist()),
    max_selections=10,
    format_func=lambda value: lookup.get(value, value),
)

rows: list[dict] = []
with st.spinner("Récupération des calendriers d'entreprises..."):
    for ticker in selected:
        bundle = fetch_calendar_bundle(ticker)
        calendar = bundle.get("calendar", {})
        for key, value in calendar.items():
            if value is None:
                continue
            values = value if isinstance(value, (list, tuple)) else [value]
            for item in values:
                timestamp = pd.to_datetime(item, errors="coerce")
                if pd.notna(timestamp):
                    rows.append({"Date": timestamp, "Ticker": ticker, "Événement": str(key), "Détail": "Calendrier société"})
        for earning in bundle.get("earnings", []):
            date_key = next((key for key in earning if "Earnings Date" in key or key.lower() in {"date", "earnings date"}), None)
            event_date = pd.to_datetime(earning.get(date_key), errors="coerce") if date_key else pd.NaT
            if pd.notna(event_date):
                estimate = earning.get("EPS Estimate", earning.get("Reported EPS", ""))
                rows.append({"Date": event_date, "Ticker": ticker, "Événement": "Résultats", "Détail": f"BPA/estimation : {estimate}"})
        for key_date in bundle.get("key_dates", []):
            event_date = pd.to_datetime(key_date.get("Date"), errors="coerce")
            if pd.notna(event_date):
                rows.append({"Date": event_date, "Ticker": ticker, "Événement": key_date.get("Evenement", "Date clé"), "Détail": f"{key_date.get('Detail', '')}"})
        for dividend in bundle.get("dividends", []):
            event_date = pd.to_datetime(dividend.get("Date"), errors="coerce")
            if pd.notna(event_date):
                rows.append({"Date": event_date, "Ticker": ticker, "Événement": "Dividende historique", "Détail": f"{dividend.get('Dividende', '')}"})
        for split in bundle.get("splits", []):
            event_date = pd.to_datetime(split.get("Date"), errors="coerce")
            if pd.notna(event_date):
                rows.append({"Date": event_date, "Ticker": ticker, "Événement": "Fractionnement", "Détail": f"Ratio : {split.get('Ratio', '')}"})

company_events = pd.DataFrame(rows)
if not company_events.empty:
    company_events["Date"] = pd.to_datetime(company_events["Date"], errors="coerce", utc=True).dt.tz_convert(None)
    company_events = company_events.dropna(subset=["Date"]).sort_values("Date")

st.subheader("Événements d'entreprises")
if company_events.empty:
    st.info("Aucun événement n'a été retourné pour les titres sélectionnés.")
else:
    today = pd.Timestamp.today().normalize()
    horizon = st.slider("Fenêtre autour d'aujourd'hui (jours)", 30, 730, 365, 30)
    visible = company_events[
        company_events["Date"].between(today - pd.Timedelta(days=horizon), today + pd.Timedelta(days=horizon))
    ]
    st.dataframe(visible, hide_index=True, width="stretch")

st.subheader("Événements économiques personnalisés")
macro = get_macro_events(profile)
if macro.empty:
    macro = pd.DataFrame(
        [
            {
                "event_date": date.today().isoformat(),
                "title": "Décision de la Banque du Canada",
                "category": "Banque centrale",
                "notes": "Mettre à jour la date à partir du calendrier officiel.",
            }
        ]
    )
else:
    macro = macro[["event_date", "title", "category", "notes"]]
macro["event_date"] = pd.to_datetime(macro["event_date"], errors="coerce").dt.date

edited = st.data_editor(
    macro,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    column_config={
        "event_date": st.column_config.DateColumn("Date", required=True),
        "title": st.column_config.TextColumn("Événement", required=True),
        "category": st.column_config.SelectboxColumn(
            "Catégorie",
            options=["Banque centrale", "Inflation", "Emploi", "PIB", "Résultats", "Autre"],
        ),
        "notes": st.column_config.TextColumn("Notes"),
    },
)

if st.button("💾 Enregistrer les événements macro", type="primary"):
    saved = edited.copy()
    saved["event_date"] = pd.to_datetime(saved["event_date"], errors="coerce").dt.date.astype(str)
    replace_macro_events(profile, saved)
    st.success("Calendrier macro enregistré dans SQLite.")

st.caption(
    "Le calendrier automatique utilise uniquement des sources publiques officielles et gratuites. Les événements personnalisés restent disponibles pour compléter les dates internes ou locales."
)

footer()
