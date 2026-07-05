from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from core.data import load_constituents
from core.insider_trades import (
    build_insider_summary,
    build_symbol_link_matrix,
    collect_insider_trades,
    fetch_finnhub_insider_transactions,
    fetch_yahoo_insider_transactions,
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
    "Repérez les achats, ventes et déclarations d’initiés sur les titres canadiens suivis par Anatole.",
    "🕵️",
)

st.caption(
    "Lecture informationnelle seulement. Les déclarations d’initiés canadiennes doivent toujours être vérifiées dans les sources officielles avant toute décision."
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
    ["Radar univers", "Titre spécifique", "Répertoire TSX", "Sources & méthode"],
    default="Radar univers",
    selection_mode="single",
)


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
        return f"{sign}{value / 1_000_000_000:.2f} G$"
    if value >= 1_000_000:
        return f"{sign}{value / 1_000_000:.2f} M$"
    if value >= 1_000:
        return f"{sign}{value / 1_000:.1f} k$"
    return f"{sign}{value:,.0f} $"


def _render_summary_cards(frame: pd.DataFrame) -> None:
    summary = build_insider_summary(frame)
    a, b, c, d = st.columns(4)
    a.metric("Transactions", f"{summary['transactions']}")
    b.metric("Sociétés touchées", f"{summary['companies']}")
    c.metric("Ratio achats", f"{summary['buy_ratio']:.0f}%")
    d.metric("Flux net estimé", _format_money(summary["net_value"]))


def _render_trades_table(frame: pd.DataFrame, key: str) -> None:
    if frame.empty:
        st.info("Aucune transaction d’initié disponible avec les sources actives pour cette sélection.")
        return
    show = frame.copy()
    for column in ["Actions", "Prix", "Valeur"]:
        show[column] = pd.to_numeric(show[column], errors="coerce")
    st.dataframe(
        show,
        hide_index=True,
        width="stretch",
        key=key,
        column_config={
            "Lien": st.column_config.LinkColumn("Lien source", display_text="Ouvrir"),
            "Valeur": st.column_config.NumberColumn("Valeur", format="$%.0f"),
            "Prix": st.column_config.NumberColumn("Prix", format="$%.2f"),
            "Actions": st.column_config.NumberColumn("Actions", format="%.0f"),
        },
    )


if section == "Radar univers":
    st.subheader("Radar des transactions récentes")
    st.write(
        "Cette vue consolide les transactions disponibles pour l’univers actif. "
        "Elle privilégie les données locales ou API; les sources publiques sans clé peuvent être limitées pour éviter de ralentir tout le Composite."
    )

    f1, f2, f3, f4 = st.columns([1, 1, 1, 1])
    with f1:
        days = st.selectbox("Période", [30, 60, 90, 180, 365], index=3, format_func=lambda x: f"{x} jours")
    with f2:
        max_symbols = st.number_input(
            "Titres à sonder",
            min_value=5,
            max_value=max(5, min(250, len(constituents))),
            value=min(25, len(constituents)),
            step=5,
            help="Cap volontaire pour garder Anatole rapide. La vue Titre spécifique couvre tout l’univers sur demande.",
        )
    with f3:
        include_yahoo = st.toggle(
            "Sonde Yahoo public",
            value=False,
            help="Sans API, cette source peut être bloquée ou lente. Active-la pour sonder les premiers titres de l’univers.",
        )
    with f4:
        include_finnhub = st.toggle(
            "Finnhub si configuré",
            value=True,
            help="Utilise FINNHUB_API_KEY si la clé est disponible dans l’environnement.",
        )

    sector_options = ["Tous"] + sorted([x for x in constituents.get("Secteur", pd.Series(dtype=str)).dropna().astype(str).unique() if x])
    selected_sector = st.selectbox("Secteur", sector_options, index=0)
    scoped = constituents if selected_sector == "Tous" else constituents[constituents["Secteur"].astype(str) == selected_sector]

    with st.spinner("Consolidation des transactions d’initiés…"):
        trades, sources = collect_insider_trades(
            scoped,
            days=int(days),
            include_yahoo=bool(include_yahoo),
            include_finnhub=bool(include_finnhub),
            max_public_symbols=int(max_symbols),
        )

    st.caption(f"Univers actif : {current_universe().label} · {len(scoped)} titres · période : {days} jours.")
    _render_summary_cards(trades)
    _render_trades_table(trades, key="insider_radar_table")

    with st.expander("État des sources"):
        st.dataframe(sources, hide_index=True, width="stretch")

    if trades.empty:
        st.warning(
            "Pour une couverture complète du Composite, ajoute un fichier data/insider_trades.csv ou configure une source API. "
            "Sans clé, Anatole peut quand même ouvrir les sources officielles par titre dans les vues Titre spécifique et Répertoire TSX."
        )

elif section == "Titre spécifique":
    st.subheader("Transactions par titre")
    st.write("Sélectionne n’importe quel titre de l’univers actif, y compris TSX Composite et TSX 60, puis charge les transactions disponibles.")

    options = constituents["Ticker"].tolist()
    selected = st.selectbox(
        "Titre",
        options,
        index=0,
        format_func=lambda value: (
            value
            + " — "
            + str(constituents.loc[constituents["Ticker"] == value, "Nom"].iloc[0])
            if value in set(constituents["Ticker"])
            else value
        ),
    )
    row = constituents[constituents["Ticker"] == selected].head(1)
    company = str(row["Nom"].iloc[0]) if not row.empty and "Nom" in row else selected

    c1, c2, c3 = st.columns(3)
    c1.link_button("Ouvrir SEDI", sedi_issuer_search_url(company), width="stretch")
    c2.link_button("Ouvrir TMX", tmx_insider_url(selected), width="stretch")
    c3.link_button("Ouvrir Yahoo", yahoo_insider_url(selected), width="stretch")

    q1, q2, q3 = st.columns([1, 1, 1])
    with q1:
        days = st.selectbox("Période analysée", [30, 60, 90, 180, 365], index=3, format_func=lambda x: f"{x} jours", key="single_days")
    with q2:
        use_yahoo = st.toggle("Yahoo public", value=True, key="single_yahoo")
    with q3:
        use_finnhub = st.toggle("Finnhub si configuré", value=True, key="single_finnhub")

    frames: list[pd.DataFrame] = []
    source_rows: list[dict[str, str]] = []

    local, local_status = load_local_insider_trades()
    source_rows.append(local_status)
    if not local.empty:
        local = local[local["Ticker"].map(normalise_ticker) == selected]
        if not local.empty:
            frames.append(local)

    if use_yahoo:
        with st.spinner(f"Lecture Yahoo Finance pour {selected}…"):
            yahoo_frame, yahoo_status = fetch_yahoo_insider_transactions(selected)
        source_rows.append(yahoo_status)
        if not yahoo_frame.empty:
            frames.append(yahoo_frame)

    if use_finnhub:
        finnhub_frame, finnhub_status = fetch_finnhub_insider_transactions(selected, days=int(days))
        source_rows.append(finnhub_status)
        if not finnhub_frame.empty:
            frames.append(finnhub_frame)

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame()
    combined = enrich_with_companies(deduplicate_trades(filter_recent(combined, days=int(days))), constituents)

    _render_summary_cards(combined)
    _render_trades_table(combined, key="insider_single_table")

    with st.expander("État des sources pour ce titre", expanded=True):
        st.dataframe(pd.DataFrame(source_rows), hide_index=True, width="stretch")

elif section == "Répertoire TSX":
    st.subheader("Répertoire de vérification par titre")
    st.write(
        "Cette matrice couvre tous les titres de l’univers actif et donne les liens de vérification. "
        "Elle est utile lorsque les sources publiques ne retournent pas automatiquement les transactions."
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
            "Yahoo": st.column_config.LinkColumn("Yahoo", display_text="Ouvrir"),
            "SEDI": st.column_config.LinkColumn("SEDI", display_text="Ouvrir"),
            "TMX": st.column_config.LinkColumn("TMX", display_text="Ouvrir"),
        },
    )

else:
    st.subheader("Sources & méthode")
    st.markdown(
        """
        **Sources utilisées par Anatole :**

        - **SEDI** : source officielle canadienne pour les déclarations d'initiés. Anatole fournit un accès de vérification parce que SEDI ne propose pas de flux simple et stable pour scanner automatiquement tout le marché.
        - **TMX Insider Trades by Symbol** : résumé quotidien par symbole basé sur les marqueurs de transactions fournis par les courtiers. Ce n'est pas toujours le même niveau de détail nominatif qu'un dépôt SEDI.
        - **Yahoo Finance public** : source publique non garantie, utile en appoint sur un titre précis.
        - **Finnhub** : source optionnelle si `FINNHUB_API_KEY` est configurée.
        - **Fichier local** : `data/insider_trades.csv`, recommandé pour une couverture propre et contrôlée du TSX Composite.

        **Colonnes attendues pour le fichier local :**
        `Date, Ticker, Société, Insider, Rôle, Transaction, Actions, Prix, Valeur, Source, Lien`
        """
    )
    st.info(
        "Le module ne transforme jamais une transaction d'initié en recommandation. "
        "Un achat d'initié peut être intéressant à analyser, mais il doit être croisé avec le contexte financier, la liquidité, la taille de la transaction et les dépôts officiels."
    )

footer()
