from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from core.analytics import market_pulse
from core.charts import heatmap_figure, market_breadth_chart, sector_performance_chart
from core.config import TORONTO_TZ
from core.universe import current_universe, current_universe_key
from core.data import load_constituents
from core.data_quality import render_data_quality_strip
from core.database import get_watchlist
from core.device import mobile_chart_height, mobile_is_lite, mobile_page_limit
from core.public_beta import current_context
from core.performance import load_timer, perf_caption, safe_display_count
from core.live_quote import render_live_quote_panel, remember_live_selection, current_live_selection
from core.runtime import load_light_market_bundle, load_technical_bundle
from core.summary import daily_market_summary
from core.ui import (
    apply_style,
    configure_page,
    footer,
    home_launchpad,
    page_header,
    sidebar_context,
    skeleton_cards,
    summary_card,
    ticker_tape,
    plotly_mobile_config,
)
from core.utils import format_money, market_status, safe_float
from core.workspaces import active_workspace


def _fmt_home_pct(value: object) -> str:
    try:
        number = float(value)
    except Exception:
        return "N/D"
    return f"{number:+.2f}%"


def _fmt_home_money(value: object) -> str:
    try:
        number = float(value)
    except Exception:
        return "N/D"
    return f"${number:,.2f}"


def render_mobile_market_map(frame: pd.DataFrame) -> None:
    """Carte marché mobile sans zoom Plotly, avec accès rapide aux fiches."""
    if frame.empty:
        st.info("Aucun titre ne correspond aux filtres.")
        return

    st.markdown("### Carte mobile")
    st.caption(
        "Vue tactile optimisée : les actions sont regroupées par secteur et "
        "restent lisibles sans zoom ni déplacement involontaire."
    )

    work = frame.copy()
    work["Variation"] = pd.to_numeric(work.get("Variation"), errors="coerce")
    work["PoidsIndice"] = pd.to_numeric(work.get("PoidsIndice"), errors="coerce").fillna(0)
    sector_summary = (
        work.groupby("Secteur", as_index=False)
        .agg(
            Variation=("Variation", "mean"),
            Poids=("PoidsIndice", "sum"),
            Titres=("Ticker", "count"),
        )
        .sort_values("Variation", ascending=False)
    )

    for _, sector_row in sector_summary.iterrows():
        sector_name = str(sector_row.get("Secteur", "Autre"))
        sector_frame = (
            work.loc[work["Secteur"] == sector_name]
            .sort_values(["PoidsIndice", "Variation"], ascending=[False, False])
            .head(10)
        )
        label = (
            f"{sector_name} · {_fmt_home_pct(sector_row.get('Variation'))} · "
            f"{int(sector_row.get('Titres', 0))} titres"
        )
        with st.expander(label, expanded=False):
            for i, row in sector_frame.iterrows():
                ticker = str(row.get("Ticker", "N/D"))
                name = str(row.get("Nom", ""))
                change = _fmt_home_pct(row.get("Variation"))
                price = _fmt_home_money(row.get("Prix"))
                button_label = f"{ticker} · {change} · {price}"
                if st.button(button_label, key=f"mobile_heatmap_open_{sector_name}_{ticker}_{i}", width="stretch"):
                    st.session_state.selected_ticker = str(row.get("YahooTicker", ticker))
                    st.switch_page("screens/14_Focus.py")
                if name:
                    st.caption(name)


def render_heatmap_focus_selector(frame: pd.DataFrame, key_prefix: str) -> None:
    """Sélecteur propre pour ouvrir une fiche depuis la carte statique."""
    if frame.empty:
        return
    candidates = frame.copy()
    candidates["VariationAbs"] = pd.to_numeric(candidates.get("Variation"), errors="coerce").abs()
    candidates = candidates.sort_values(["VariationAbs", "PoidsIndice"], ascending=[False, False]).head(80)
    options = [
        (
            f"{row.get('Ticker', '')} — {row.get('Nom', '')} "
            f"({_fmt_home_pct(row.get('Variation'))})"
        )
        for _, row in candidates.iterrows()
    ]
    if not options:
        return
    selected = st.selectbox(
        "Recherche rapide dans la carte",
        options,
        index=None,
        placeholder="Chercher une action affichée sur la carte…",
        key=f"{key_prefix}_focus_selector",
    )
    if selected:
        ticker = selected.split(" — ", 1)[0].strip()
        match = candidates[candidates["Ticker"].astype(str) == ticker]
        if not match.empty:
            row = match.iloc[0]
            payload = {
                "ticker": str(row.get("Ticker", ticker)),
                "yahoo": str(row.get("YahooTicker", ticker)),
                "name": str(row.get("Nom", "")),
                "sector": str(row.get("Secteur", "")),
            }
            _store_cross_page_ticker(payload)
            render_live_quote_panel(
                payload["yahoo"],
                symbol=payload["ticker"],
                name=payload["name"],
                sector=payload["sector"],
                key_prefix=f"{key_prefix}_search_live",
            )
            _render_cross_page_actions(payload, key_prefix=f"{key_prefix}_search_actions")


def _normalise_symbol(value: object) -> str:
    """Retourne un symbole lisible pour les communications entre pages."""
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "." in text:
        text = text.split(".", 1)[0]
    return text.replace("-", ".")


def _extract_selected_heatmap_ticker(event: object, frame: pd.DataFrame) -> dict[str, str] | None:
    """Extrait le titre cliqué dans la treemap Plotly, avec fallback robuste."""
    if event is None or frame is None or frame.empty:
        return None

    event_dict = event
    try:
        if hasattr(event, "to_dict"):
            event_dict = event.to_dict()
    except Exception:
        event_dict = event

    selection = {}
    if isinstance(event_dict, dict):
        selection = event_dict.get("selection") or {}
    else:
        selection = getattr(event_dict, "selection", {}) or {}

    points = []
    if isinstance(selection, dict):
        points = selection.get("points") or []
    else:
        points = getattr(selection, "points", []) or []
    if not points:
        return None

    work = frame.copy()
    if "Ticker" not in work:
        return None
    work["__TickerClean"] = work["Ticker"].map(_normalise_symbol)
    work["__YahooClean"] = work.get("YahooTicker", work["Ticker"]).map(_normalise_symbol)

    for point in points:
        if not isinstance(point, dict):
            try:
                point = dict(point)
            except Exception:
                continue
        candidates: list[str] = []
        custom = point.get("customdata") or point.get("custom_data") or []
        if isinstance(custom, (list, tuple)):
            for item in custom:
                candidates.append(str(item or ""))
        for key in ["label", "id", "parent", "entry", "pointNumber"]:
            if key in point:
                candidates.append(str(point.get(key) or ""))
        for raw in candidates:
            # Une treemap peut renvoyer des ids du type "Financials/RY".
            for part in str(raw).replace("\\", "/").split("/"):
                token = _normalise_symbol(part)
                if not token:
                    continue
                match = work[(work["__TickerClean"] == token) | (work["__YahooClean"] == token)]
                if not match.empty:
                    row = match.iloc[0]
                    return {
                        "ticker": str(row.get("Ticker", token)),
                        "yahoo": str(row.get("YahooTicker", row.get("Ticker", token))),
                        "name": str(row.get("Nom", "")),
                        "sector": str(row.get("Secteur", "")),
                    }
    return None


def _store_cross_page_ticker(payload: dict[str, str]) -> None:
    """Alimente les pages cibles avec le titre choisi."""
    ticker = str(payload.get("ticker") or "").strip()
    yahoo = str(payload.get("yahoo") or ticker).strip()
    if not ticker:
        return
    st.session_state["anatole_bridge_ticker"] = ticker
    st.session_state["anatole_bridge_yahoo"] = yahoo
    st.session_state["anatole_bridge_name"] = str(payload.get("name") or "")
    st.session_state["anatole_bridge_sector"] = str(payload.get("sector") or "")

    # Clés déjà utilisées ou faciles à consommer par les pages existantes.
    st.session_state["selected_ticker"] = yahoo
    st.session_state["focus_ticker"] = yahoo
    st.session_state["screener_symbol_query"] = ticker
    st.session_state["insider_symbol_query"] = ticker
    st.session_state["alert_prefill_ticker"] = yahoo
    st.session_state["watchlist_prefill_ticker"] = yahoo
    remember_live_selection(payload)


def _switch_to_ticker_destination(destination: str, payload: dict[str, str]) -> None:
    _store_cross_page_ticker(payload)
    destinations = {
        "Screener": "screens/1_Screener.py",
        "Focus": "screens/14_Focus.py",
        "Insiders": "screens/25_Insiders.py",
        "Alertes": "screens/4_Alertes.py",
        "Watchlist": "screens/9_Watchlist.py",
    }
    path = destinations.get(destination, "screens/1_Screener.py")
    try:
        st.switch_page(path)
    except Exception:
        st.info("Le titre est mémorisé. Ouvre la section souhaitée depuis la navigation pour continuer l’analyse.")


def _render_cross_page_actions(payload: dict[str, str], key_prefix: str) -> None:
    """Affiche une barre d’actions quand une action est sélectionnée."""
    if not payload:
        return
    ticker = str(payload.get("ticker") or "").strip()
    name = str(payload.get("name") or "").strip()
    sector = str(payload.get("sector") or "").strip()
    if not ticker:
        return
    st.success(
        f"{ticker} sélectionné" + (f" · {name}" if name else "") + (f" · {sector}" if sector else "")
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if st.button("Ouvrir Screener", key=f"{key_prefix}_go_screener", width="stretch"):
            _switch_to_ticker_destination("Screener", payload)
    with c2:
        if st.button("Mode Focus", key=f"{key_prefix}_go_focus", width="stretch"):
            _switch_to_ticker_destination("Focus", payload)
    with c3:
        if st.button("Insiders", key=f"{key_prefix}_go_insiders", width="stretch"):
            _switch_to_ticker_destination("Insiders", payload)
    with c4:
        if st.button("Alerte", key=f"{key_prefix}_go_alertes", width="stretch"):
            _switch_to_ticker_destination("Alertes", payload)
    with c5:
        if st.button("Liste", key=f"{key_prefix}_go_watchlist", width="stretch"):
            _switch_to_ticker_destination("Watchlist", payload)



configure_page("Vue d'ensemble", "📈")
apply_style()
profile = sidebar_context()
page_header(
    "Anatole",
    "Bienvenue sur Anatole, votre cockpit de lecture du marché canadien en bêta publique.",
    show_hero_search=True,
    hero_search_profile=profile,
)

workspace_name, workspace_layout = active_workspace(profile)
visible_modules = {
    str(item.get("module"))
    for item in workspace_layout
    if bool(item.get("visible", False))
}
st.caption(f"Espace de travail actif : {workspace_name}")

if bool(st.session_state.get("show_quick_links", False)):
    home_launchpad()

constituents, diagnostics = load_constituents()
is_open, _ = market_status()
refresh_seconds = int(st.session_state.get("refresh_seconds", 60))
only_open = bool(st.session_state.get("refresh_only_market_open", True))
refresh_rule = f"{refresh_seconds}s" if (is_open or not only_open) else None


@st.fragment(run_every=refresh_rule)
def live_cockpit() -> None:
    placeholder = st.empty()
    with placeholder.container():
        skeleton_cards(5, 78)

    with load_timer("cockpit"):
        constituents_live, live_diagnostics, market = load_light_market_bundle()
    placeholder.empty()

    if market.empty:
        st.error(
            "Les données de marché ne sont pas disponibles. "
            "Réessaie dans quelques instants."
        )
        return

    universe_key = str(live_diagnostics.get("universe_key") or current_universe_key())
    universe_label = str(live_diagnostics.get("universe_label") or current_universe().label)
    render_data_quality_strip(market, live_diagnostics, compact=True)
    if live_diagnostics.get("status") in {"Univers partiel", "Technique partiel"}:
        st.warning(
            f"{universe_label} est affiché en mode partiel. "
            "Anatole ne remplace plus automatiquement cette sélection par le TSX 60."
        )
    perf_caption("cockpit", threshold=2.2)

    source_values = set(
        market.get("SourceCours", pd.Series(dtype=str))
        .dropna()
        .astype(str)
        .tolist()
    )
    if "Dernière donnée disponible" in source_values:
        st.caption(
            "Certaines cotations proviennent du dernier snapshot valide "
            "pendant une indisponibilité temporaire de la source."
        )

    valid = market.dropna(subset=["Variation"]).copy()
    weights = pd.to_numeric(valid.get("PoidsIndice", 1), errors="coerce").fillna(1)
    weighted_change = np.average(valid["Variation"], weights=weights) if not valid.empty else np.nan
    advancers = int((valid["Variation"] > 0).sum())
    decliners = int((valid["Variation"] < 0).sum())
    sector = valid.groupby("Secteur", as_index=False)["Variation"].mean().sort_values("Variation", ascending=False)
    best_sector = sector.iloc[0]["Secteur"] if not sector.empty else "N/D"
    best_sector_change = sector.iloc[0]["Variation"] if not sector.empty else np.nan
    worst_sector = sector.iloc[-1]["Secteur"] if not sector.empty else "N/D"
    worst_sector_change = sector.iloc[-1]["Variation"] if not sector.empty else np.nan
    top_mover = valid.nlargest(1, "Variation").head(1)
    drag_mover = valid.nsmallest(1, "Variation").head(1)
    top_label = "N/D" if top_mover.empty else f"{top_mover.iloc[0].get('Ticker', 'N/D')} {safe_float(top_mover.iloc[0].get('Variation')):+.2f}%"
    drag_label = "N/D" if drag_mover.empty else f"{drag_mover.iloc[0].get('Ticker', 'N/D')} {safe_float(drag_mover.iloc[0].get('Variation')):+.2f}%"

    st.markdown(
        f"""
        <div class="sky-home-grid">
            <div class="sky-home-panel">
                <div class="sky-home-panel-title">Lecture du marché</div>
                <div class="sky-home-panel-value">{weighted_change:+.2f}%</div>
                <div class="sky-home-panel-text">{advancers} titres en hausse · {decliners} en baisse</div>
            </div>
            <div class="sky-home-panel">
                <div class="sky-home-panel-title">Secteur dominant</div>
                <div class="sky-home-panel-value">{best_sector}</div>
                <div class="sky-home-panel-text">{best_sector_change:+.2f}% en moyenne</div>
            </div>
            <div class="sky-home-panel">
                <div class="sky-home-panel-title">Titre moteur</div>
                <div class="sky-home-panel-value">{top_label}</div>
                <div class="sky-home-panel-text">Plus forte contribution indicative de la séance</div>
            </div>
            <div class="sky-home-panel">
                <div class="sky-home-panel-title">Risque à surveiller</div>
                <div class="sky-home-panel-value">{worst_sector}</div>
                <div class="sky-home-panel-text">{worst_sector_change:+.2f}% · frein principal : {drag_label}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if bool(st.session_state.get("show_ticker", False)):
        movers = pd.concat(
            [valid.nlargest(4, "Variation"), valid.nsmallest(4, "Variation")],
            ignore_index=True,
        ).drop_duplicates(subset=["YahooTicker"])
        ticker_tape(
            [
                {
                    "ticker": str(row.get("Ticker", row.get("YahooTicker", ""))),
                    "price": format_money(row.get("Prix")),
                    "change": safe_float(row.get("Variation")),
                }
                for _, row in movers.iterrows()
            ]
        )

    if "Market Pulse" in visible_modules or not visible_modules:
        metrics = st.columns(5)
        metrics[0].metric(f"{current_universe().short_label} indicatif", f"{weighted_change:+.2f}%" if not np.isnan(weighted_change) else "N/D")
        metrics[1].metric("Titres en hausse", advancers)
        metrics[2].metric("Titres en baisse", decliners)
        metrics[3].metric("Meilleur secteur", best_sector, f"{best_sector_change:+.2f}%" if not np.isnan(best_sector_change) else None)
        metrics[4].metric("Mise à jour", datetime.now(TORONTO_TZ).strftime("%H:%M ET"))
        summary_card(daily_market_summary(market))

    overview_left, overview_right = st.columns([1.9, 1])
    with overview_left:
        sector_chart = sector_performance_chart(market)
        st.plotly_chart(
            sector_chart,
            width="stretch",
            key=f"accueil_performance_secteurs_{universe_key}",
            config=plotly_mobile_config(),
        )
    with overview_right:
        if "Watchlist" in visible_modules:
            st.subheader("Watchlist")
            watchlist = get_watchlist(profile)
            watch = market[market["YahooTicker"].isin(watchlist)].copy()
            if watch.empty:
                st.caption("Ta watchlist est vide ou ses cotations ne sont pas disponibles.")
            else:
                cols = [column for column in ["Ticker", "Prix", "Variation"] if column in watch]
                st.dataframe(
                    watch[cols].sort_values("Variation", ascending=False),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Prix": st.column_config.NumberColumn(format="$%.2f"),
                        "Variation": st.column_config.NumberColumn(format="%+.2f%%"),
                    },
                )
            st.page_link("screens/9_Watchlist.py", label="Ouvrir la watchlist", width="stretch")
        else:
            st.subheader("Espace actif")
            module_paths = {
                "Moteurs du marché": "screens/15_Market_Drivers.py",
                "Actualités": "screens/5_Actualites.py",
                "Alertes": "screens/4_Alertes.py",
                "Portefeuille": "screens/3_Portefeuille.py",
                "Graphique Focus": "screens/14_Focus.py",
                "Screener": "screens/1_Screener.py",
                "Calendrier": "screens/6_Calendrier.py",
                "Corrélations": "screens/8_Correlations.py",
            }
            linked = 0
            for item in sorted(workspace_layout, key=lambda entry: entry.get("order", 999)):
                module = str(item.get("module"))
                if not item.get("visible") or module not in module_paths or linked >= 5:
                    continue
                st.page_link(module_paths[module], label=module, width="stretch")
                linked += 1
            if linked == 0:
                st.page_link("screens/11_Workspaces.py", label="Configurer l'espace", width="stretch")

    if "Heatmap" not in visible_modules and visible_modules:
        return

    st.subheader("Carte du marché")
    with st.expander("Filtres de la carte", expanded=False):
        all_sectors = sorted(market["Secteur"].dropna().unique().tolist())
        c1, c2, c3, c4 = st.columns([2.1, 1, 1, 1.25])
        with c1:
            selected_sectors = st.multiselect(
                "Secteurs",
                all_sectors,
                default=all_sectors,
                key="minimal_heatmap_sectors",
            )
        with c2:
            min_move = st.slider(
                "Mouvement minimum (%)",
                0.0,
                10.0,
                0.0,
                0.1,
                key="minimal_heatmap_move",
            )
        with c3:
            cinema = st.toggle("Vue agrandie", value=False, key="minimal_heatmap_cinema")
        with c4:
            readable_default = 0 if mobile_is_lite() else 1
            size_choice = st.radio(
                "Taille des cases",
                ["Lisible", "Pondérée"],
                index=readable_default,
                horizontal=True,
                key="minimal_heatmap_size_mode",
                help="Lisible donne une case visible à chaque action. Pondérée reflète davantage le poids indicatif du titre.",
            )

    filtered = market[
        market["Secteur"].isin(selected_sectors)
        & (market["Variation"].abs().fillna(0) >= min_move)
    ].copy()
    if filtered.empty:
        st.info("Aucun titre ne correspond aux filtres.")
    else:
        # La carte reste la vraie treemap sur mobile comme sur ordinateur.
        # Sur téléphone, on agrandit la hauteur et on verrouille les gestes de
        # zoom/pan pour éviter les déplacements irrécupérables.
        is_mobile_map = mobile_is_lite()
        mobile_count_height = int(max(980, min(2600, len(filtered) * 11)))
        desktop_height = 820 if cinema else 620
        height = mobile_count_height if is_mobile_map else desktop_height
        readable_mode = (size_choice == "Lisible")
        figure = heatmap_figure(
            filtered,
            height=height,
            mobile_readable=is_mobile_map or readable_mode,
            size_mode="equal" if readable_mode else "weight",
        )
        st.caption(
            "Cliquez sur une action pour afficher immédiatement sa cotation et sa variation live. "
            "Vous pourrez ensuite poursuivre vers Focus, Screener, Insiders, Alertes ou la Watchlist."
        )

        plotly_event = None
        chart_key = f"minimal_heatmap_{universe_key}_{len(filtered)}_{size_choice}_clickable"
        try:
            plotly_event = st.plotly_chart(
                figure,
                width="stretch",
                key=chart_key,
                config=plotly_mobile_config(interactive=True),
                on_select="rerun",
                selection_mode="points",
            )
        except TypeError:
            st.plotly_chart(
                figure,
                width="stretch",
                key=chart_key,
                config=plotly_mobile_config(interactive=True),
            )

        selected_payload = _extract_selected_heatmap_ticker(plotly_event, filtered)
        if selected_payload:
            _store_cross_page_ticker(selected_payload)

        st.caption(
            f"Carte complète : {len(filtered)} titres affichés selon l’univers et les filtres actifs. "
            "Si ton navigateur ne transmet pas le clic sur la carte, utilise la recherche rapide ci-dessous."
        )
        render_heatmap_focus_selector(filtered, key_prefix=f"minimal_heatmap_{universe_key}")
        last_payload = selected_payload or current_live_selection()
        if last_payload:
            render_live_quote_panel(
                last_payload.get("yahoo", last_payload.get("ticker", "")),
                symbol=last_payload.get("ticker", ""),
                name=last_payload.get("name", ""),
                sector=last_payload.get("sector", ""),
                key_prefix=f"minimal_heatmap_live_{universe_key}",
            )
            _render_cross_page_actions(last_payload, key_prefix=f"minimal_heatmap_last_{universe_key}")

    with st.expander("Principaux mouvements", expanded=False):
        left, right = st.columns(2)
        columns = [column for column in ["Ticker", "Nom", "Prix", "Variation"] if column in market]
        with left:
            st.markdown("**Hausses**")
            st.dataframe(market.nlargest(mobile_page_limit(8, 5), "Variation")[columns], hide_index=True, width="stretch")
        with right:
            st.markdown("**Baisses**")
            st.dataframe(market.nsmallest(mobile_page_limit(8, 5), "Variation")[columns], hide_index=True, width="stretch")


live_cockpit()

show_advanced = bool(st.session_state.get("show_advanced_home", False)) or st.session_state.get("experience_mode") == "advanced"
with st.expander("Analyse technique du marché", expanded=show_advanced):
    load_advanced = st.checkbox(
        "Charger la largeur technique et les moyennes mobiles",
        value=show_advanced,
        help="Ce calcul télécharge l'historique des titres de l'univers actif. Sur mobile, laisse cette option fermée si tu veux une page plus rapide.",
    )
    if load_advanced:
        with st.spinner("Calcul de la largeur technique…"):
            _, _, _, features = load_technical_bundle()
        pulse = market_pulse(features)
        cols = st.columns(4)
        cols[0].metric("Au-dessus SMA50", f"{pulse.get('above_sma50_pct', np.nan):.0f}%")
        cols[1].metric("Au-dessus SMA200", f"{pulse.get('above_sma200_pct', np.nan):.0f}%")
        cols[2].metric("Nouveaux sommets", pulse.get("new_highs", 0))
        cols[3].metric("Volume relatif", f"{pulse.get('relative_volume', np.nan):.2f}x")
        st.plotly_chart(market_breadth_chart(features), width="stretch", key=f"accueil_largeur_marche_{current_universe_key()}")

expected = diagnostics.get("expected")
actual = int(diagnostics.get("actual", 0) or 0)
if expected and actual != int(expected):
    missing_count = max(0, int(expected) - actual)
    st.warning(
        f"La composition récupérée contient {actual} titres "
        f"sur {expected}. Anatole continue avec les titres disponibles."
    )

    beta_context = current_context()
    if beta_context.is_admin:
        st.page_link(
            "screens/10_Diagnostics.py",
            label="Ouvrir les diagnostics",
            icon="🛠️",
        )
    else:
        plural = "titre est temporairement indisponible" if missing_count == 1 else "titres sont temporairement indisponibles"
        st.caption(
            f"{missing_count} {plural}. Le détail technique est réservé aux administrateurs."
        )
elif actual:
    st.caption(
        f"Univers actif : {diagnostics.get('universe_label', current_universe().label)} · "
        f"{actual} titres dans la composition · "
        f"{diagnostics.get('displayed', actual)} titres affichés dans le cockpit."
    )

footer()
