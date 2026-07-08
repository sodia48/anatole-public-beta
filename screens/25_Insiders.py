from __future__ import annotations

import math
import os

import pandas as pd
import streamlit as st

from core.data import load_constituents
from core.insider_trades import (
    build_insider_summary,
    build_symbol_link_matrix,
    collect_insider_trades,
    fetch_finnhub_insider_transactions,
    fetch_yahoo_insider_transactions,
    fetch_marketbeat_insider_transactions,
    fetch_insiderscreener_transactions,
    marketbeat_insider_url,
    canadian_insider_url,
    insiderscreener_company_url,
    filter_recent,
    enrich_with_companies,
    deduplicate_trades,
    load_local_insider_trades,
    normalise_ticker,
    yahoo_insider_url,
    sedi_issuer_search_url,
    tmx_insider_url,
)
from core.performance import load_timer, perf_caption
from core.ui import apply_style, configure_page, footer, page_header, sidebar_context
from core.universe import current_universe

configure_page("Transactions d’initiés", "🕵️")
apply_style()
profile = sidebar_context()
page_header(
    "Transactions d’initiés",
    "Repérez les achats, ventes et déclarations d’initiés sur les sociétés canadiennes suivies par Anatole.",
    "🕵️",
)

st.caption(
    "Vue informative. Anatole consolide des sources publiques et officielles quand elles sont accessibles, puis normalise les résultats pour faciliter la vérification."
)

with load_timer("insider_constituents"):
    constituents, diagnostics = load_constituents()
perf_caption("insider_constituents", threshold=1.5)

if constituents.empty:
    st.warning("L’univers de titres est indisponible pour le moment.")
    footer()
    st.stop()

constituents = constituents.copy()
constituents["Ticker"] = constituents["Ticker"].map(normalise_ticker)
constituents = constituents.drop_duplicates("Ticker")

section = st.segmented_control(
    "Vue",
    ["Radar univers", "Titre spécifique", "Répertoire TSX", "Méthodologie"],
    default="Radar univers",
    selection_mode="single",
)


def _format_decimal_fr(value: float, decimals: int = 2, suffix: str = "") -> str:
    try:
        if value is None or math.isnan(float(value)):
            return "N/D"
        number = float(value)
    except Exception:
        return "N/D"

    sign = "-" if number < 0 else ""
    number = abs(number)
    formatted = f"{number:,.{decimals}f}"
    formatted = formatted.replace(",", " ").replace(".", ",")
    return f"{sign}{formatted}{suffix}"


def _format_currency_fr(value: float, decimals: int = 2) -> str:
    text = _format_decimal_fr(value, decimals=decimals)
    return "N/D" if text == "N/D" else f"{text} $"


def _format_money(value: float) -> str:
    try:
        if value is None or math.isnan(float(value)):
            return "N/D"
        value = float(value)
    except Exception:
        return "N/D"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}{_format_decimal_fr(value / 1_000_000_000, 2)} G$"
    if value >= 1_000_000:
        return f"{sign}{_format_decimal_fr(value / 1_000_000, 2)} M$"
    if value >= 1_000:
        return f"{sign}{_format_decimal_fr(value / 1_000, 1)} k$"
    return f"{sign}{_format_currency_fr(value, 2)}"


def _quality_label(frame: pd.DataFrame, source_count: int = 0) -> str:
    if frame is None or frame.empty:
        return "À vérifier"
    if len(frame) >= 10 and source_count >= 2:
        return "Élevée"
    if len(frame) >= 3:
        return "Bonne"
    return "Partielle"


def _clean_source_statuses(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Source", "État", "Couverture"])

    result = frame.copy()
    for col in ["Source", "État", "Détail"]:
        if col not in result.columns:
            result[col] = ""

    def status_label(raw: str) -> str:
        text = str(raw or "").lower()
        if any(token in text for token in ["ok", "connecté", "connected"]):
            return "Connectée"
        if any(token in text for token in ["aucune transaction", "aucune donnée", "vide"]):
            return "Aucune transaction détectée"
        if any(token in text for token in ["non activ", "inactive", "inactif", "sur demande"]):
            return "Disponible sur demande"
        if any(token in text for token in ["limité", "non disponible", "indisponible"]):
            return "Couverture limitée aujourd’hui"
        return str(raw or "À vérifier")

    def coverage_label(row: pd.Series) -> str:
        source = str(row.get("Source", ""))
        state = status_label(str(row.get("État", "")))
        if state == "Connectée":
            return "Données normalisées disponibles."
        if state == "Aucune transaction détectée":
            return "Aucun mouvement détecté dans la période sélectionnée."
        if "Import" in source:
            return "Aucun relevé interne n’a été importé."
        if state == "Disponible sur demande":
            return "Source consultable au cas par cas ou via connecteur."
        return "La source ne permet pas une lecture automatisée fiable aujourd’hui."

    output = pd.DataFrame(
        {
            "Source": result["Source"].astype(str).replace({"Fichier local": "Import interne", "Yahoo Finance public": "Source publique"}),
            "État": result["État"].map(status_label),
        }
    )
    output["Couverture"] = result.apply(coverage_label, axis=1)
    return output.drop_duplicates().reset_index(drop=True)


def _render_summary_cards(frame: pd.DataFrame, source_rows: pd.DataFrame | None = None) -> None:
    summary = build_insider_summary(frame)
    source_count = 0
    if source_rows is not None and not source_rows.empty and "Source" in source_rows:
        source_count = int(source_rows["Source"].nunique())
    a, b, c, d = st.columns(4)
    a.metric("Transactions", f"{summary['transactions']}")
    b.metric("Sociétés touchées", f"{summary['companies']}")
    c.metric("Ratio achats", f"{summary['buy_ratio']:.0f}%")
    d.metric("Flux net estimé", _format_money(summary["net_value"]))
    e, f = st.columns(2)
    e.metric("Confiance donnée", _quality_label(frame, source_count))
    connected = 0
    if source_rows is not None and not source_rows.empty and "État" in source_rows:
        connected = int(source_rows["État"].astype(str).str.contains("Connecté", case=False, na=False).sum())
    f.metric("Sources actives", f"{connected}/{source_count}")


def _render_empty_state(company: str | None = None, ticker: str | None = None) -> None:
    name = company or ticker or "ce titre"
    st.info(
        f"Aucune transaction normalisée n’a été détectée pour {name} dans les sources publiques disponibles aujourd’hui. "
        "Anatole affiche aussi les liens de vérification officiels pour confirmer la situation au besoin."
    )


def _render_trades_table(frame: pd.DataFrame, key: str) -> None:
    if frame.empty:
        return

    show = frame.copy()
    numeric_actions = pd.to_numeric(show.get("Actions"), errors="coerce")
    numeric_price = pd.to_numeric(show.get("Prix"), errors="coerce")
    numeric_value = pd.to_numeric(show.get("Valeur"), errors="coerce")

    # Affichage lisible en français : séparateur de milliers, virgule décimale, deux décimales.
    # Exemple : 3000 -> 3 000,00 ; 97.47 -> 97,47 $ ; 292410 -> 292 410,00 $.
    show["Actions"] = numeric_actions.map(lambda value: _format_decimal_fr(value, 2))
    show["Prix"] = numeric_price.map(lambda value: _format_currency_fr(value, 2))
    show["Valeur"] = numeric_value.map(lambda value: _format_currency_fr(value, 2))

    st.dataframe(
        show,
        hide_index=True,
        width="stretch",
        key=key,
        column_config={
            "Actions": st.column_config.TextColumn("Actions"),
            "Prix": st.column_config.TextColumn("Prix"),
            "Valeur": st.column_config.TextColumn("Valeur"),
            "Lien": st.column_config.LinkColumn("Source", display_text="Ouvrir"),
        },
    )


def _render_source_health(source_rows: pd.DataFrame, expanded: bool = False) -> None:
    clean = _clean_source_statuses(source_rows)
    if clean.empty:
        return
    with st.expander("Couverture des sources", expanded=expanded):
        st.dataframe(clean, hide_index=True, width="stretch")


if section == "Radar univers":
    st.subheader("Radar des transactions récentes")
    st.write(
        "Cette vue synthétise les mouvements d’initiés détectés dans l’univers actif. "
        "Elle sert à repérer des signaux à vérifier, pas à formuler une recommandation."
    )

    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        days = st.selectbox("Période", [30, 60, 90, 180, 365], index=3, format_func=lambda x: f"{x} jours")
    with f2:
        max_symbols = st.number_input(
            "Titres sondés",
            min_value=5,
            max_value=max(5, min(250, len(constituents))),
            value=min(25, len(constituents)),
            step=5,
            help="Limite volontaire pour conserver une expérience rapide. La vue par titre permet une vérification ciblée sur tout l’univers.",
        )
    with f3:
        public_scan = st.toggle(
            "Scan public automatique",
            value=True,
            help="Interroge automatiquement les sources publiques exploitables sur les premiers titres affichés.",
        )

    sector_options = ["Tous"] + sorted([x for x in constituents.get("Secteur", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    selected_sector = st.selectbox("Secteur", sector_options, index=0)
    scoped = constituents if selected_sector == "Tous" else constituents[constituents["Secteur"].astype(str) == selected_sector]

    with st.spinner("Analyse des transactions d’initiés…"):
        trades, sources = collect_insider_trades(
            scoped,
            days=int(days),
            include_yahoo=False,
            include_finnhub=False,
            include_marketbeat=bool(public_scan),
            include_insiderscreener=bool(public_scan),
            max_public_symbols=int(max_symbols),
        )

    st.caption(f"Univers actif : {current_universe().label} · {len(scoped)} titres · période : {days} jours.")
    _render_summary_cards(trades, sources)
    if trades.empty:
        _render_empty_state()
    else:
        _render_trades_table(trades, key="insider_radar_table")
    _render_source_health(sources, expanded=False)

elif section == "Titre spécifique":
    st.subheader("Analyse par titre")
    st.write("Sélectionnez une société de l’univers actif pour consulter les données disponibles et ouvrir les sources officielles de vérification.")

    options = constituents["Ticker"].tolist()
    ticker_set = set(options)
    selected = st.selectbox(
        "Titre",
        options,
        index=0,
        format_func=lambda value: (
            value
            + " — "
            + str(constituents.loc[constituents["Ticker"] == value, "Nom"].iloc[0])
            if value in ticker_set and "Nom" in constituents.columns
            else value
        ),
    )
    row = constituents[constituents["Ticker"] == selected].head(1)
    company = str(row["Nom"].iloc[0]) if not row.empty and "Nom" in row else selected

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.link_button("SEDI", sedi_issuer_search_url(company), width="stretch")
    c2.link_button("TMX", tmx_insider_url(selected), width="stretch")
    c3.link_button("MarketBeat", marketbeat_insider_url(selected), width="stretch")
    c4.link_button("InsiderScreener", insiderscreener_company_url(selected, company), width="stretch")
    c5.link_button("Canadian Insider", canadian_insider_url(selected), width="stretch")

    q1, q2 = st.columns([1, 2])
    with q1:
        days = st.selectbox("Période analysée", [30, 60, 90, 180, 365], index=3, format_func=lambda x: f"{x} jours", key="single_days")
    with q2:
        with st.expander("Options de recherche", expanded=False):
            use_public = st.toggle("Sources publiques automatiques", value=True, key="single_public_sources")
            use_yahoo = st.toggle("Yahoo en source complémentaire", value=False, key="single_yahoo")
            use_finnhub = st.toggle("Connecteur professionnel si disponible", value=False, key="single_finnhub")

    frames: list[pd.DataFrame] = []
    source_rows: list[dict[str, str]] = []

    local, local_status = load_local_insider_trades()
    source_rows.append(local_status)
    if not local.empty:
        local = local[local["Ticker"].map(normalise_ticker) == selected]
        if not local.empty:
            frames.append(local)

    if use_public:
        with st.spinner(f"Recherche des transactions disponibles pour {selected}…"):
            marketbeat_frame, marketbeat_status = fetch_marketbeat_insider_transactions(selected, company=company)
            screener_frame, screener_status = fetch_insiderscreener_transactions(selected, company=company)
        source_rows.extend([marketbeat_status, screener_status])
        if not marketbeat_frame.empty:
            frames.append(marketbeat_frame)
        if not screener_frame.empty:
            frames.append(screener_frame)
    else:
        source_rows.extend([
            {"Source": "MarketBeat public", "État": "Sur demande", "Détail": "Lecture automatique désactivée pour cette recherche."},
            {"Source": "InsiderScreener public", "État": "Sur demande", "Détail": "Lecture automatique désactivée pour cette recherche."},
        ])

    if use_yahoo:
        yahoo_frame, yahoo_status = fetch_yahoo_insider_transactions(selected)
        source_rows.append(yahoo_status)
        if not yahoo_frame.empty:
            frames.append(yahoo_frame)

    if use_finnhub and os.getenv("FINNHUB_API_KEY", ""):
        finnhub_frame, finnhub_status = fetch_finnhub_insider_transactions(selected, days=int(days))
        source_rows.append(finnhub_status)
        if not finnhub_frame.empty:
            frames.append(finnhub_frame)
    elif use_finnhub:
        source_rows.append(
            {
                "Source": "Connecteur professionnel",
                "État": "Disponible sur demande",
                "Détail": "Connexion non activée dans cet environnement.",
            }
        )

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    combined = enrich_with_companies(deduplicate_trades(filter_recent(combined, days=int(days))), constituents)
    source_frame = pd.DataFrame(source_rows)

    _render_summary_cards(combined, source_frame)
    if combined.empty:
        _render_empty_state(company=company, ticker=selected)
    else:
        _render_trades_table(combined, key="insider_single_table")
    _render_source_health(source_frame, expanded=False)

elif section == "Répertoire TSX":
    st.subheader("Répertoire de vérification")
    st.write(
        "Cette matrice donne un accès rapide aux sources de vérification pour chaque titre de l’univers actif. "
        "Elle est utile lorsque la donnée normalisée n’est pas encore disponible automatiquement."
    )
    search = st.text_input("Filtrer par symbole, société ou secteur", placeholder="RY, Banque Royale, Énergie…")
    matrix = build_symbol_link_matrix(constituents)
    if search.strip():
        mask = matrix.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, na=False)).any(axis=1)
        matrix = matrix[mask].copy()
    st.caption(f"{len(matrix)} titres affichés sur {len(constituents)} dans {current_universe().label}.")
    st.dataframe(
        matrix,
        hide_index=True,
        width="stretch",
        column_config={
            "SEDI": st.column_config.LinkColumn("SEDI", display_text="Ouvrir"),
            "TMX": st.column_config.LinkColumn("TMX", display_text="Ouvrir"),
            "MarketBeat": st.column_config.LinkColumn("MarketBeat", display_text="Ouvrir"),
            "InsiderScreener": st.column_config.LinkColumn("InsiderScreener", display_text="Ouvrir"),
            "Canadian Insider": st.column_config.LinkColumn("Canadian Insider", display_text="Ouvrir"),
        },
    )

else:
    st.subheader("Méthodologie")
    st.markdown(
        """
        **Objectif du module**

        Le module suit les transactions d’initiés comme un signal d’information : achats, ventes, exercices d’options et déclarations liées aux dirigeants, administrateurs ou personnes apparentées.

        **Sources privilégiées**

        - **SEDI** : source officielle canadienne de vérification.
        - **TMX** : accès rapide par symbole aux informations de marché liées aux transactions d’initiés.
        - **MarketBeat public** : source publique exploitée automatiquement quand la page du titre est disponible.
        - **InsiderScreener public** : source publique complémentaire pour détecter les transactions et signaux récents.
        - **Canadian Insider** : source canadienne utile pour la vérification manuelle et le contexte INK/SEDI.
        - **Import interne** : permet de charger un relevé validé pour une couverture contrôlée du TSX Composite.

        **Lecture du signal**

        Un achat d’initié peut indiquer de la confiance, mais il peut aussi être isolé ou peu significatif. Une vente peut refléter une diversification personnelle, des impôts, une rémunération en actions ou une décision stratégique. Anatole ne transforme donc jamais une transaction d’initié en recommandation d’achat ou de vente.
        """
    )

footer()
