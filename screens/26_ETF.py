from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from core.etf_directory import load_etf_directory, sector_map_frame, etf_summary
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context


configure_page("ETF sectoriels", "🧺")
apply_style()
sidebar_context()
page_header(
    "ETF sectoriels",
    "Explorez les FNB cotés au Canada par secteur, marché, émetteur et exposition.",
    "🧺",
)


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


def fmt_pct(value: object) -> str:
    if _is_missing(value):
        return "—"
    try:
        number = float(value)
    except Exception:
        return "—"
    return f"{number:,.2f} %".replace(",", " ").replace(".", ",")


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
    display["Variation"] = display["Variation"].map(fmt_pct)
    display["Volume"] = display["Volume"].map(fmt_int)
    return display[columns].rename(
        columns={
            "Ticker": "Symbole",
            "Variation": "Variation jour",
            "Rôle": "Utilité",
        }
    )


with st.spinner("Préparation du catalogue ETF…"):
    directory = load_etf_directory(include_prices=True)

summary = etf_summary(directory)

k1, k2, k3, k4 = st.columns(4)
k1.metric("ETF suivis", f"{summary['total']}")
k2.metric("Cotés TSX", f"{summary['tsx']}")
k3.metric("Sectoriels / thématiques", f"{summary['sector']}")
k4.metric("Émetteurs", f"{summary['issuers']}")

st.info(
    "Cette section sert à repérer des véhicules d’exposition par secteur. "
    "Elle ne remplace pas l’analyse du prospectus, des frais, de la liquidité et de la composition du fonds."
)

section = st.segmented_control(
    "Vue",
    ["Cartographie sectorielle", "ETF cotés TSX", "Comparer", "Méthode"],
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

elif section == "Comparer":
    st.subheader("Comparer des ETF")
    st.write("Sélectionnez plusieurs ETF pour comparer rapidement leur exposition et leur mouvement du jour.")
    options = [f"{row.Ticker} — {row.Nom}" for row in directory.itertuples(index=False)]
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
        - identifier les fonds sectoriels, thématiques, dividendes, commodités et marchés larges ;
        - surveiller le prix et la variation lorsque les données de marché sont disponibles.

        **À vérifier avant toute décision**

        - composition du fonds ;
        - frais de gestion ;
        - liquidité ;
        - devise ;
        - concentration sectorielle ;
        - horizon et risque de l’investisseur.
        """
    )

footer()
