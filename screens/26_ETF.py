from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import streamlit as st

from core.etf_directory import (
    estimate_etf_contributors,
    etf_history_summary,
    etf_summary,
    load_etf_directory,
    load_etf_history,
    load_etf_holdings,
    sector_map_frame,
)
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("ETF sectoriels", "🧺")
apply_style()
sidebar_context()
page_header(
    "ETF sectoriels",
    "Explorez les FNB cotés au Canada par secteur, puis analysez leur évolution historique et leurs principaux moteurs.",
    "🧺",
    show_universe_selector=False,
)


PERIODS = {
    "1 mois": "1mo",
    "3 mois": "3mo",
    "6 mois": "6mo",
    "1 an": "1y",
    "2 ans": "2y",
    "5 ans": "5y",
}


def _is_missing(value: object) -> bool:
    try:
        return value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value)
    except Exception:
        return value is None


def fmt_money(value: object) -> str:
    if _is_missing(value):
        return "—"
    try:
        number = float(value)
    except Exception:
        return "—"
    return f"{number:,.2f} $".replace(",", " ").replace(".", ",")


def fmt_pct(value: object, signed: bool = False) -> str:
    if _is_missing(value):
        return "—"
    try:
        number = float(value)
    except Exception:
        return "—"
    pattern = "+,.2f" if signed else ",.2f"
    return f"{number:{pattern}} %".replace(",", " ").replace(".", ",")


def fmt_weight(value: object) -> str:
    return fmt_pct(value)


def fmt_points(value: object) -> str:
    if _is_missing(value):
        return "—"
    try:
        number = float(value)
    except Exception:
        return "—"
    return f"{number:+,.2f} pts".replace(",", " ").replace(".", ",")


def fmt_int(value: object) -> str:
    if _is_missing(value):
        return "—"
    try:
        number = float(value)
    except Exception:
        return "—"
    return f"{number:,.0f}".replace(",", " ")


def _display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    display = frame.copy()
    columns = [
        "Ticker",
        "Nom",
        "Émetteur",
        "Famille",
        "Secteur",
        "Région",
        "Exposition",
        "Prix",
        "Variation",
        "Volume",
        "Rôle",
    ]
    for column in columns:
        if column not in display.columns:
            display[column] = pd.NA
    display["Prix"] = display["Prix"].map(fmt_money)
    display["Variation"] = display["Variation"].map(lambda value: fmt_pct(value, signed=True))
    display["Volume"] = display["Volume"].map(fmt_int)
    return display[columns].rename(
        columns={
            "Ticker": "Symbole",
            "Variation": "Variation jour",
            "Rôle": "Utilité",
        }
    )


def _option_label(row: object) -> str:
    return f"{row.Ticker} — {row.Nom}"


def _selected_etf_row(directory: pd.DataFrame, selected: str) -> pd.Series:
    ticker = selected.split(" — ", 1)[0].strip().upper()
    matched = directory[directory["Ticker"].astype(str).str.upper().eq(ticker)]
    if matched.empty:
        return directory.iloc[0]
    return matched.iloc[0]


def _format_contributor_frame(frame: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    columns = ["Ticker", "Nom", "Poids", "Performance", "Contribution estimée", "SourcePositions"]
    display = frame.copy().head(limit)
    for column in columns:
        if column not in display.columns:
            display[column] = pd.NA
    display["Poids"] = display["Poids"].map(fmt_weight)
    display["Performance"] = display["Performance"].map(lambda value: fmt_pct(value, signed=True))
    display["Contribution estimée"] = display["Contribution estimée"].map(fmt_points)
    display["SourcePositions"] = display["SourcePositions"].replace(
        {
            "Profil indicatif": "Profil indicatif",
            "Données publiques": "Source publique",
            "Catalogue positions": "Catalogue interne",
        }
    )
    return display[columns].rename(
        columns={
            "Ticker": "Symbole",
            "Poids": "Poids dans l’ETF",
            "Performance": "Performance du titre",
            "Contribution estimée": "Contribution estimée",
            "SourcePositions": "Source composition",
        }
    )


with st.spinner("Préparation du catalogue ETF…"):
    directory = load_etf_directory(include_prices=True)

if directory.empty:
    st.warning("Le catalogue ETF est temporairement indisponible.")
    footer()
    st.stop()

summary = etf_summary(directory)

k1, k2, k3, k4 = st.columns(4)
k1.metric("ETF suivis", f"{summary['total']}")
k2.metric("Cotés TSX", f"{summary['tsx']}")
k3.metric("Sectoriels / thématiques", f"{summary['sector']}")
k4.metric("Émetteurs", f"{summary['issuers']}")

st.info(
    "Cette section sert à repérer des véhicules d’exposition par secteur et à comprendre ce qui a porté leur performance. "
    "Les contributions par titre sont des estimations basées sur les principales positions disponibles et les variations de prix."
)

section = st.segmented_control(
    "Vue",
    ["Cartographie sectorielle", "ETF cotés TSX", "Analyse historique", "Comparer", "Méthode"],
    default="Cartographie sectorielle",
    selection_mode="single",
)

if section == "Cartographie sectorielle":
    st.subheader("Cartographie des secteurs")
    st.write(
        "Utilisez cette vue pour passer rapidement d’un secteur économique à des ETF canadiens ou mondiaux cotés au Canada."
    )
    st.dataframe(sector_map_frame(), hide_index=True, width="stretch")

    st.subheader("ETF sectoriels et thématiques")
    sector_frame = directory[
        directory["Famille"].astype(str).str.contains("Secteur|Thématique", case=False, regex=True)
    ].copy()
    sectors = ["Tous"] + sorted(sector_frame["Secteur"].dropna().astype(str).unique().tolist())
    selected_sector = st.selectbox("Secteur", sectors)
    if selected_sector != "Tous":
        sector_frame = sector_frame[sector_frame["Secteur"].astype(str).eq(selected_sector)]
    st.dataframe(_display_frame(sector_frame), hide_index=True, width="stretch")

elif section == "ETF cotés TSX":
    st.subheader("Répertoire des ETF cotés au Canada")
    left, middle, right = st.columns([1, 1, 1])
    with left:
        families = ["Tous"] + sorted(directory["Famille"].dropna().astype(str).unique().tolist())
        selected_family = st.selectbox("Famille", families)
    with middle:
        issuers = ["Tous"] + sorted(directory["Émetteur"].dropna().astype(str).unique().tolist())
        selected_issuer = st.selectbox("Émetteur", issuers)
    with right:
        query = st.text_input("Recherche", placeholder="XEG, banques, énergie, dividendes…")

    filtered = directory.copy()
    if selected_family != "Tous":
        filtered = filtered[filtered["Famille"].astype(str).eq(selected_family)]
    if selected_issuer != "Tous":
        filtered = filtered[filtered["Émetteur"].astype(str).eq(selected_issuer)]
    if query.strip():
        q = query.strip().lower()
        mask = pd.Series(False, index=filtered.index)
        for column in ["Ticker", "Nom", "Émetteur", "Famille", "Secteur", "Région", "Exposition", "Rôle"]:
            if column in filtered.columns:
                mask = mask | filtered[column].astype(str).str.lower().str.contains(q, regex=False)
        filtered = filtered[mask]

    st.caption(f"{len(filtered)} ETF affiché(s).")
    st.dataframe(_display_frame(filtered), hide_index=True, width="stretch")

    st.download_button(
        "Télécharger la liste",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="anatole_etf_directory.csv",
        mime="text/csv",
        width="stretch",
    )

elif section == "Analyse historique":
    st.subheader("Évolution historique d’un ETF")
    st.write(
        "Sélectionnez un ETF pour voir son évolution en base 100 et les principales actions qui ont contribué à la performance sur la période choisie."
    )

    left, right = st.columns([2, 1])
    with left:
        options = [_option_label(row) for row in directory.itertuples(index=False)]
        default_index = next((i for i, item in enumerate(options) if item.startswith("XIC")), 0)
        selected = st.selectbox("ETF à analyser", options, index=default_index)
    with right:
        selected_period_label = st.selectbox("Période", list(PERIODS.keys()), index=3)

    period = PERIODS[selected_period_label]
    etf_row = _selected_etf_row(directory, selected)
    etf_ticker = str(etf_row.get("Ticker", "")).upper()
    etf_yahoo = str(etf_row.get("YahooTicker", ""))

    title_left, title_right = st.columns([2, 1])
    with title_left:
        st.markdown(f"### {etf_ticker} — {etf_row.get('Nom', '')}")
        st.caption(
            f"{etf_row.get('Émetteur', '—')} · {etf_row.get('Famille', '—')} · {etf_row.get('Exposition', '—')}"
        )

    history = load_etf_history(etf_yahoo, period=period)
    summary_history = etf_history_summary(history)
    with title_right:
        st.metric("Rendement période", fmt_pct(summary_history.get("return"), signed=True))
        st.metric("Repli maximal", fmt_pct(summary_history.get("drawdown"), signed=True))

    if history.empty:
        st.warning("L’historique de prix est temporairement indisponible pour cet ETF.")
    else:
        chart_frame = history.copy()
        chart_frame["Date"] = pd.to_datetime(chart_frame["Date"], errors="coerce")
        fig = px.line(
            chart_frame,
            x="Date",
            y="Base 100",
            title=f"Évolution de {etf_ticker} — base 100",
            labels={"Base 100": "Base 100", "Date": "Date"},
        )
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=55, b=10))
        st.plotly_chart(fig, width="stretch")

        hist_display = chart_frame.tail(8).copy()
        hist_display["Prix"] = hist_display["Prix"].map(fmt_money)
        hist_display["Rendement"] = hist_display["Rendement"].map(lambda value: fmt_pct(value, signed=True))
        hist_display["Repli depuis sommet"] = hist_display["Repli depuis sommet"].map(lambda value: fmt_pct(value, signed=True))
        st.dataframe(
            hist_display[["Date", "Prix", "Rendement", "Repli depuis sommet"]].rename(
                columns={"Repli depuis sommet": "Repli vs sommet"}
            ),
            hide_index=True,
            width="stretch",
        )

    st.subheader("Principaux moteurs de performance")
    contributors = estimate_etf_contributors(etf_ticker, etf_yahoo, period=period)

    if contributors.empty:
        st.info(
            "Les principales positions ne sont pas disponibles automatiquement pour cet ETF. "
            "Un catalogue de positions validé permettra d’obtenir une attribution plus précise."
        )
    elif contributors["Contribution estimée"].dropna().empty:
        holdings = load_etf_holdings(etf_ticker, etf_yahoo)
        st.info(
            "La composition principale est disponible, mais les variations des titres sous-jacents ne sont pas accessibles pour cette période."
        )
        st.dataframe(_format_contributor_frame(holdings, limit=15), hide_index=True, width="stretch")
    else:
        pos = contributors[contributors["Contribution estimée"].fillna(0).ge(0)].sort_values(
            "Contribution estimée", ascending=False
        )
        neg = contributors[contributors["Contribution estimée"].fillna(0).lt(0)].sort_values(
            "Contribution estimée", ascending=True
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Contributions positives")
            st.dataframe(_format_contributor_frame(pos, limit=8), hide_index=True, width="stretch")
        with c2:
            st.markdown("#### Freins principaux")
            st.dataframe(_format_contributor_frame(neg, limit=8), hide_index=True, width="stretch")

        chart = contributors.dropna(subset=["Contribution estimée"]).copy().head(12)
        if not chart.empty:
            chart["Libellé"] = chart["Ticker"].astype(str) + " — " + chart["Nom"].astype(str).str.slice(0, 28)
            fig2 = px.bar(
                chart.sort_values("Contribution estimée"),
                x="Contribution estimée",
                y="Libellé",
                orientation="h",
                title="Contribution estimée des principales positions",
                labels={"Contribution estimée": "Points de rendement estimés", "Libellé": "Titre"},
            )
            fig2.update_layout(height=460, margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(fig2, width="stretch")

        source = contributors["SourcePositions"].dropna().astype(str).unique().tolist()
        if source and "Profil indicatif" in source:
            st.caption(
                "Certaines positions proviennent d’un profil indicatif intégré lorsque les sources publiques ne retournent pas de composition exploitable. "
                "Pour une attribution officielle, utilisez la fiche du fournisseur ou ajoutez un fichier de positions validé."
            )

elif section == "Comparer":
    st.subheader("Comparer des ETF")
    st.write("Sélectionnez plusieurs ETF pour comparer rapidement leur exposition et leur mouvement du jour.")
    options = [_option_label(row) for row in directory.itertuples(index=False)]
    default = [opt for opt in options if opt.startswith(("XIC", "XFN", "XEG", "XIT"))][:4]
    selected = st.multiselect("ETF à comparer", options, default=default, max_selections=8)
    tickers = [item.split(" — ", 1)[0] for item in selected]
    compare = directory[directory["Ticker"].isin(tickers)].copy()
    st.dataframe(_display_frame(compare), hide_index=True, width="stretch")

    if not compare.empty and "Variation" in compare.columns:
        chart = compare[["Ticker", "Variation"]].copy()
        chart["Variation"] = pd.to_numeric(chart["Variation"], errors="coerce")
        chart = chart.dropna(subset=["Variation"])
        if not chart.empty:
            st.bar_chart(chart.set_index("Ticker"), width="stretch")

else:
    st.subheader("Méthode")
    st.write(
        "Le catalogue Anatole regroupe des ETF utiles pour comprendre les secteurs du marché canadien, "
        "les grandes expositions mondiales cotées au Canada et certains thèmes suivis par les investisseurs."
    )
    st.markdown(
        """
        **Ce que la page permet de faire**

        - repérer rapidement un ETF par secteur ;
        - comparer les expositions canadiennes, américaines et mondiales ;
        - suivre l’évolution historique d’un ETF en base 100 ;
        - estimer les principales actions qui ont porté ou freiné la performance ;
        - identifier les fonds sectoriels, thématiques, dividendes, commodités et marchés larges.

        **Comment lire les contributions**

        L’attribution est une estimation simple : poids de la position × performance du titre sur la période. Elle sert à comprendre les grands moteurs du fonds, mais ne remplace pas une attribution officielle du fournisseur.

        **À vérifier avant toute décision**

        - composition officielle du fonds ;
        - frais de gestion ;
        - liquidité ;
        - devise ;
        - concentration sectorielle ;
        - horizon et risque de l’investisseur.
        """
    )

footer()
