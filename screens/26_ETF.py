from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import streamlit as st

from core.etf_directory import (
    estimate_etf_contributors,
    etf_detail_sources,
    etf_history_summary,
    etf_summary,
    load_etf_directory,
    load_etf_history,
    load_etf_holdings,
    load_etf_quote,
    sector_map_frame,
)
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context, plotly_mobile_config


configure_page("ETF sectoriels", "🧺")
apply_style()
sidebar_context()
page_header(
    "ETF sectoriels",
    "Explorez les FNB cotés au Canada par secteur, puis analysez leur évolution historique et leurs principaux moteurs.",
    "🧺",
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




def _search_etfs(directory: pd.DataFrame, query: str, limit: int = 12) -> pd.DataFrame:
    """Return a compact, ranked ETF search result set."""
    if directory.empty:
        return directory.copy()

    frame = directory.copy()
    q = str(query or "").strip().lower()

    if not q:
        preferred = [
            "XIC", "XIU", "ZCN", "VCN", "XFN", "ZEB", "XEG", "ZEO",
            "XIT", "XMA", "XGD", "XRE", "XUT", "XST", "VFV", "XUS",
        ]
        preferred_rank = {ticker: i for i, ticker in enumerate(preferred)}
        frame["_rank"] = frame["Ticker"].astype(str).str.upper().map(preferred_rank).fillna(999)
        return frame.sort_values(["_rank", "Ticker"]).drop(columns=["_rank"], errors="ignore").head(limit)

    searchable_columns = [
        "Ticker", "Nom", "Émetteur", "Famille", "Secteur", "Région", "Exposition", "Rôle"
    ]
    score = pd.Series(0, index=frame.index, dtype="int64")
    ticker_text = frame.get("Ticker", pd.Series("", index=frame.index)).astype(str).str.lower()

    score += ticker_text.eq(q).astype(int) * 100
    score += ticker_text.str.startswith(q).astype(int) * 70
    score += ticker_text.str.contains(q, regex=False).astype(int) * 45

    for column in searchable_columns:
        if column not in frame.columns:
            continue
        values = frame[column].astype(str).str.lower()
        score += values.eq(q).astype(int) * 35
        score += values.str.startswith(q).astype(int) * 25
        score += values.str.contains(q, regex=False).astype(int) * 12

    matches = frame[score.gt(0)].copy()
    if matches.empty:
        return matches
    matches["_score"] = score.loc[matches.index]
    return matches.sort_values(["_score", "Ticker"], ascending=[False, True]).drop(columns=["_score"], errors="ignore").head(limit)


def _compact_search_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    columns = ["Ticker", "Nom", "Émetteur", "Secteur", "Exposition", "Rôle"]
    display = frame.copy()
    for column in columns:
        if column not in display.columns:
            display[column] = pd.NA
    return display[columns].rename(
        columns={
            "Ticker": "Symbole",
            "Rôle": "Utilité",
        }
    )

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




def _safe_float(value: object) -> float | None:
    if _is_missing(value):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if math.isnan(number):
        return None
    return number


def _ticker_tokens(value: object) -> list[str]:
    raw = str(value or "")
    tokens: list[str] = []
    for chunk in raw.replace(";", ",").split(","):
        token = chunk.strip().upper()
        if token and token != "—" and token not in tokens:
            tokens.append(token)
    return tokens


def _select_etf(ticker: str) -> None:
    value = str(ticker or "").upper().strip()
    if value:
        st.session_state["etf_detail_ticker"] = value


def _selected_etf_detail_row(directory: pd.DataFrame, fallback: str = "XIC") -> pd.Series:
    ticker = str(st.session_state.get("etf_detail_ticker") or fallback).upper().strip()
    matched = directory[directory["Ticker"].astype(str).str.upper().eq(ticker)]
    if matched.empty:
        matched = directory[directory["Ticker"].astype(str).str.upper().eq(str(fallback).upper())]
    if matched.empty:
        return directory.iloc[0]
    return matched.iloc[0]


def _format_holdings_frame(frame: pd.DataFrame, limit: int = 25) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    display = frame.copy().head(limit)
    for column in ["Ticker", "Nom", "Poids", "Secteur", "SourcePositions"]:
        if column not in display.columns:
            display[column] = pd.NA
    display["Poids"] = display["Poids"].map(fmt_weight)
    display["SourcePositions"] = display["SourcePositions"].replace(
        {
            "Profil indicatif": "Profil indicatif",
            "Données publiques": "Source publique",
            "Catalogue positions": "Catalogue validé",
        }
    )
    return display[["Ticker", "Nom", "Poids", "Secteur", "SourcePositions"]].rename(
        columns={
            "Ticker": "Symbole",
            "Poids": "Poids",
            "SourcePositions": "Source composition",
        }
    )


def _render_etf_buttons(tickers: list[str], directory: pd.DataFrame, prefix: str, limit: int = 20) -> None:
    clean = []
    directory_tickers = set(directory["Ticker"].astype(str).str.upper().tolist())
    for ticker in tickers:
        t = str(ticker or "").upper().strip()
        if t and t in directory_tickers and t not in clean:
            clean.append(t)
    if not clean:
        return
    cols = st.columns(4)
    for idx, ticker in enumerate(clean[:limit]):
        row = directory[directory["Ticker"].astype(str).str.upper().eq(ticker)].head(1)
        name = str(row.iloc[0].get("Nom", "")) if not row.empty else ticker
        with cols[idx % 4]:
            if st.button(f"Ouvrir {ticker}", key=f"{prefix}_{ticker}_{idx}", width="stretch", help=name):
                _select_etf(ticker)


def _show_etf_detail_panel(directory: pd.DataFrame, ticker: str | None = None, period: str = "1y") -> None:
    if directory.empty:
        return
    if ticker:
        _select_etf(ticker)
    row = _selected_etf_detail_row(directory)
    etf_ticker = str(row.get("Ticker", "")).upper().strip()
    etf_yahoo = str(row.get("YahooTicker", "")).strip()
    if not etf_ticker:
        return

    quote = load_etf_quote(etf_ticker, etf_yahoo)
    holdings = load_etf_holdings(etf_ticker, etf_yahoo)

    st.markdown("---")
    st.subheader(f"Fiche ETF — {etf_ticker}")
    st.caption(
        f"{row.get('Nom', '')} · {row.get('Émetteur', '—')} · {row.get('Famille', '—')} · {row.get('Exposition', '—')}"
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Prix", fmt_money(quote.get("Prix")))
    m2.metric("Variation", fmt_pct(quote.get("VariationPct"), signed=True))
    m3.metric("Volume", fmt_int(quote.get("Volume")))
    m4.metric("Haut jour", fmt_money(quote.get("HautJour")))
    m5.metric("Bas jour", fmt_money(quote.get("BasJour")))

    st.caption(
        "Prix disponible via les sources de marché intégrées. Selon la source et la bourse, les données peuvent être en direct ou différées."
    )

    link_cols = st.columns(2)
    sources = etf_detail_sources(etf_ticker, etf_yahoo)
    with link_cols[0]:
        st.link_button("Ouvrir la fiche Yahoo Finance", sources.get("Yahoo Finance", "#"), width="stretch")
    with link_cols[1]:
        st.link_button("Ouvrir la fiche TMX", sources.get("TMX Money", "#"), width="stretch")

    tabs = st.tabs(["Prix", "Composition", "Moteurs", "Lecture"])
    with tabs[0]:
        hist = load_etf_history(etf_yahoo, period=period)
        if hist.empty:
            st.info("L’historique de prix est temporairement indisponible pour cet ETF.")
        else:
            chart_frame = hist.copy()
            chart_frame["Date"] = pd.to_datetime(chart_frame["Date"], errors="coerce")
            fig = px.line(
                chart_frame,
                x="Date",
                y="Base 100",
                title=f"{etf_ticker} — évolution en base 100",
                labels={"Base 100": "Base 100", "Date": "Date"},
            )
            fig.update_layout(height=430, margin=dict(l=10, r=10, t=55, b=10))
            st.plotly_chart(fig, width="stretch", config=plotly_mobile_config())

    with tabs[1]:
        if holdings.empty:
            st.info("La composition principale n’est pas disponible automatiquement pour cet ETF.")
        else:
            h = holdings.copy()
            h["Poids"] = h["Poids"].map(_safe_float)
            h = h.sort_values("Poids", ascending=False, na_position="last")
            weights = pd.to_numeric(h["Poids"], errors="coerce").dropna()
            c1, c2, c3 = st.columns(3)
            c1.metric("Positions suivies", f"{len(h)}")
            c2.metric("Poids top 5", fmt_pct(weights.head(5).sum() if not weights.empty else None))
            c3.metric("Source", str(h.get("SourcePositions", pd.Series(["—"])).dropna().astype(str).head(1).iloc[0] if not h.empty else "—"))
            st.dataframe(_format_holdings_frame(h, limit=30), hide_index=True, width="stretch")

            chart = h.dropna(subset=["Poids"]).head(15).copy()
            if not chart.empty:
                chart["Libellé"] = chart["Ticker"].astype(str) + " — " + chart["Nom"].astype(str).str.slice(0, 28)
                fig_h = px.bar(
                    chart.sort_values("Poids"),
                    x="Poids",
                    y="Libellé",
                    orientation="h",
                    title=f"Principales positions de {etf_ticker}",
                    labels={"Poids": "Poids estimé (%)", "Libellé": "Position"},
                )
                fig_h.update_layout(height=480, margin=dict(l=10, r=10, t=55, b=10))
                st.plotly_chart(fig_h, width="stretch", config=plotly_mobile_config())

    with tabs[2]:
        contributors = estimate_etf_contributors(etf_ticker, etf_yahoo, period=period)
        if contributors.empty:
            st.info("Les moteurs de performance ne sont pas disponibles pour cet ETF.")
        else:
            pos = contributors[contributors["Contribution estimée"].fillna(0).ge(0)].sort_values(
                "Contribution estimée", ascending=False
            )
            neg = contributors[contributors["Contribution estimée"].fillna(0).lt(0)].sort_values(
                "Contribution estimée", ascending=True
            )
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Actions qui ont porté l’ETF")
                st.dataframe(_format_contributor_frame(pos, limit=8), hide_index=True, width="stretch")
            with c2:
                st.markdown("#### Actions qui ont freiné l’ETF")
                st.dataframe(_format_contributor_frame(neg, limit=8), hide_index=True, width="stretch")

    with tabs[3]:
        family = str(row.get("Famille", "—"))
        exposure = str(row.get("Exposition", "—"))
        role = str(row.get("Rôle", "—"))
        st.markdown(
            f"""
            **Lecture Anatole**

            **{etf_ticker}** sert principalement à suivre : **{exposure}**.  
            Famille : **{family}**.  
            Utilité : **{role}**.

            À vérifier avant de prendre une décision : frais, liquidité, devise, concentration, composition officielle et horizon de placement.
            """
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
    ["Cartographie sectorielle", "Fiche ETF", "ETF cotés TSX", "Analyse historique", "Comparer", "Méthode"],
    default="Cartographie sectorielle",
    selection_mode="single",
)

if section == "Cartographie sectorielle":
    st.subheader("Cartographie des secteurs")
    st.write(
        "Utilisez cette vue pour passer rapidement d’un secteur économique à des ETF canadiens ou mondiaux cotés au Canada."
    )
    sector_map = sector_map_frame()
    st.dataframe(sector_map, hide_index=True, width="stretch")

    st.markdown("#### Ouvrir rapidement une fiche ETF")
    map_tickers: list[str] = []
    for column in ["ETF Canada", "ETF mondial coté TSX"]:
        if column in sector_map.columns:
            for value in sector_map[column].tolist():
                map_tickers.extend(_ticker_tokens(value))
    _render_etf_buttons(map_tickers, directory, "sector_map_etf", limit=24)
    if st.session_state.get("etf_detail_ticker"):
        _show_etf_detail_panel(directory, period="1y")

    st.subheader("ETF sectoriels et thématiques")
    sector_frame = directory[
        directory["Famille"].astype(str).str.contains("Secteur|Thématique", case=False, regex=True)
    ].copy()
    sectors = ["Tous"] + sorted(sector_frame["Secteur"].dropna().astype(str).unique().tolist())
    selected_sector = st.selectbox("Secteur", sectors)
    if selected_sector != "Tous":
        sector_frame = sector_frame[sector_frame["Secteur"].astype(str).eq(selected_sector)]
    st.dataframe(_display_frame(sector_frame), hide_index=True, width="stretch")

elif section == "Fiche ETF":
    st.subheader("Rechercher une fiche ETF")
    st.write("Cliquez sur un ETF pour afficher son prix disponible, son historique, sa composition et les principaux titres qui expliquent sa performance.")

    c_search, c_period = st.columns([2.2, 1])
    with c_search:
        query = st.text_input("Rechercher un ETF", placeholder="XIC, XFN, banques, énergie, dividendes, technologie…", key="etf_detail_search")
    with c_period:
        detail_period_label = st.selectbox("Période d’analyse", list(PERIODS.keys()), index=3, key="etf_detail_period")

    matches = _search_etfs(directory, query, limit=16)
    if matches.empty:
        st.warning("Aucun ETF ne correspond à cette recherche.")
    else:
        st.dataframe(_compact_search_frame(matches), hide_index=True, width="stretch")
        _render_etf_buttons(matches["Ticker"].astype(str).str.upper().tolist(), directory, "detail_search_etf", limit=16)
        if not st.session_state.get("etf_detail_ticker"):
            _select_etf(str(matches.iloc[0].get("Ticker", "XIC")))
        _show_etf_detail_panel(directory, period=PERIODS[detail_period_label])

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
    st.markdown("#### Cliquer pour ouvrir la fiche")
    _render_etf_buttons(filtered["Ticker"].astype(str).str.upper().tolist(), directory, "listed_etf", limit=24)
    if st.session_state.get("etf_detail_ticker"):
        _show_etf_detail_panel(directory, period="1y")

    st.download_button(
        "Télécharger la liste",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="anatole_etf_directory.csv",
        mime="text/csv",
        width="stretch",
    )

elif section == "Analyse historique":
    st.subheader("Recherche et évolution historique d’un ETF")
    st.write(
        "Recherchez un FNB par symbole, secteur, émetteur ou thème. Anatole affiche ensuite son évolution historique et les titres qui ont le plus contribué à sa performance."
    )

    search_left, period_right = st.columns([2.2, 1])
    with search_left:
        search_query = st.text_input(
            "Rechercher un ETF",
            placeholder="Ex. XIC, banques, énergie, dividendes, technologie, or…",
            key="etf_history_search_query",
        )
    with period_right:
        selected_period_label = st.selectbox("Période", list(PERIODS.keys()), index=3)

    matches = _search_etfs(directory, search_query, limit=12)

    if matches.empty:
        st.warning("Aucun ETF ne correspond à cette recherche. Essayez un symbole, un secteur ou un thème différent.")
        footer()
        st.stop()

    selected_ticker = st.session_state.get("etf_history_selected_ticker")
    available_tickers = matches["Ticker"].astype(str).str.upper().tolist()
    if selected_ticker not in available_tickers:
        selected_ticker = available_tickers[0]
        st.session_state["etf_history_selected_ticker"] = selected_ticker

    st.caption(
        "Résultats suggérés" if search_query.strip() else "Suggestions rapides — utilisez la barre de recherche pour affiner."
    )
    st.dataframe(_compact_search_frame(matches), hide_index=True, width="stretch")

    button_cols = st.columns(4)
    for idx, row in enumerate(matches.head(8).itertuples(index=False)):
        ticker = str(getattr(row, "Ticker", "")).upper()
        name = str(getattr(row, "Nom", ""))
        is_current = ticker == selected_ticker
        label = f"Analyser {ticker}" if not is_current else f"✓ {ticker}"
        with button_cols[idx % 4]:
            if st.button(label, key=f"etf_history_pick_{ticker}_{idx}", width="stretch", help=name):
                st.session_state["etf_history_selected_ticker"] = ticker
                st.session_state["etf_detail_ticker"] = ticker
                selected_ticker = ticker

    selected_rows = directory[directory["Ticker"].astype(str).str.upper().eq(str(selected_ticker).upper())]
    if selected_rows.empty:
        selected_rows = matches.head(1)
    etf_row = selected_rows.iloc[0]
    _select_etf(str(etf_row.get("Ticker", selected_ticker)))

    period = PERIODS[selected_period_label]
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
        st.plotly_chart(fig, width="stretch", config=plotly_mobile_config())

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
            st.plotly_chart(fig2, width="stretch", config=plotly_mobile_config())

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
