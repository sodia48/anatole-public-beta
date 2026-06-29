from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_plotly_events2 import plotly_events

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
)
from core.utils import format_money, market_status, safe_float
from core.workspaces import active_workspace


configure_page("Vue d'ensemble", "📈")
apply_style()
profile = sidebar_context()
page_header(
    "Anatole",
    "Hey Bud, bienvenue sur Anatole.\\nJe suis en ce moment en mode bêta.",
)

workspace_name, workspace_layout = active_workspace(profile)
visible_modules = {
    str(item.get("module"))
    for item in workspace_layout
    if bool(item.get("visible", False))
}
st.caption(f"Espace actif : {workspace_name}")

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
        st.plotly_chart(sector_performance_chart(market), width="stretch", key=f"accueil_performance_secteurs_{universe_key}")
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
        c1, c2, c3 = st.columns([2, 1, 1])
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

    filtered = market[
        market["Secteur"].isin(selected_sectors)
        & (market["Variation"].abs().fillna(0) >= min_move)
    ].copy()
    if filtered.empty:
        st.info("Aucun titre ne correspond aux filtres.")
    else:
        height = mobile_chart_height(760 if cinema else 580, 430)
        figure = heatmap_figure(filtered, height=height)
        clicks = plotly_events(
            figure,
            click_event=True,
            hover_event=False,
            select_event=False,
            override_height=height,
            key=f"minimal_heatmap_{universe_key}",
            config={
                "displaylogo": False,
                "responsive": True,
                "scrollZoom": False,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            },
        )
        st.caption("Clique sur une entreprise pour ouvrir sa fiche dédiée.")
        if clicks:
            point_number = clicks[-1].get("pointNumber", clicks[-1].get("pointIndex"))
            labels = list(figure.data[0].labels)
            if point_number is not None and 0 <= int(point_number) < len(labels):
                label = str(labels[int(point_number)])
                match = filtered[filtered["Ticker"] == label]
                if not match.empty:
                    st.session_state.selected_ticker = str(match.iloc[0]["YahooTicker"])
                    st.switch_page("screens/14_Focus.py")

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
