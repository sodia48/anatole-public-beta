from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import streamlit as st

try:  # Optional Render dependency. Anatole still runs if it is not installed.
    from streamlit_autorefresh import st_autorefresh  # type: ignore
except Exception:  # pragma: no cover - depends on deployment env
    st_autorefresh = None  # type: ignore

from core.config import TORONTO_TZ


@dataclass(frozen=True)
class LivePolicy:
    section: str
    interval_seconds: int
    label: str


DEFAULT_INTERVAL_SECONDS = 300


def _normalize(value: object) -> str:
    return str(value or "").strip().lower().replace("’", "'")


def _current_universe_key() -> str:
    try:
        from core.universe import current_universe_key

        return str(current_universe_key() or "tsx_composite")
    except Exception:
        return "tsx_composite"


def section_from_title(title: object) -> str:
    text = _normalize(title)
    if any(token in text for token in ["fiche action", "focus", "graphique", "trader"]):
        return "focus"
    if any(token in text for token in ["watchlist", "liste"]):
        return "watchlist"
    if any(token in text for token in ["screener"]):
        return "screener"
    if any(token in text for token in ["terminal pro", "terminal"]):
        return "terminal"
    if any(token in text for token in ["etf", "fnb"]):
        return "etf"
    if any(token in text for token in ["actualités", "actualites", "nouvelles"]):
        return "news"
    if any(token in text for token in ["ipo", "introductions"]):
        return "ipo"
    if any(token in text for token in ["initié", "initie", "insider"]):
        return "insiders"
    if any(token in text for token in ["psychologie", "sentiment"]):
        return "psychology"
    if any(token in text for token in ["aujourd'hui", "aujourd’hui", "brief"]):
        return "today"
    if any(token in text for token in ["anatole", "vue d'ensemble", "cockpit", "accueil"]):
        return "cockpit"
    if any(token in text for token in ["portefeuille", "alertes", "notifications"]):
        return "portfolio"
    return "standard"


def live_policy_for(section_or_title: object, universe_key: str | None = None) -> LivePolicy:
    raw = _normalize(section_or_title)
    known = {
        "focus",
        "watchlist",
        "cockpit",
        "today",
        "screener",
        "terminal",
        "etf",
        "news",
        "ipo",
        "insiders",
        "psychology",
        "portfolio",
        "standard",
    }
    section = raw if raw in known else section_from_title(section_or_title)
    universe = str(universe_key or _current_universe_key() or "tsx_composite")

    if section == "focus":
        return LivePolicy(section, 5, "Focus live")
    if section == "watchlist":
        return LivePolicy(section, 20, "Watchlist live")
    if section == "cockpit":
        seconds = 15 if universe == "tsx60" else 45
        return LivePolicy(section, seconds, "Cockpit live")
    if section == "today":
        return LivePolicy(section, 30, "Brief live")
    if section in {"screener", "terminal", "psychology"}:
        return LivePolicy(section, 45, "Analyse live")
    if section == "etf":
        return LivePolicy(section, 45, "ETF live")
    if section == "news":
        return LivePolicy(section, 900, "Actualités")
    if section == "ipo":
        return LivePolicy(section, 1800, "IPO")
    if section == "insiders":
        return LivePolicy(section, 900, "Insiders")
    if section == "portfolio":
        return LivePolicy(section, 30, "Portefeuille live")
    return LivePolicy(section, DEFAULT_INTERVAL_SECONDS, "Live")


def _inject_meta_refresh(seconds: int) -> None:
    # Fallback sans dépendance. Certains navigateurs honorent ce meta refresh
    # même rendu dans le body; si ce n'est pas le cas, Anatole reste stable.
    try:
        st.markdown(
            f'<meta http-equiv="refresh" content="{int(seconds)}">',
            unsafe_allow_html=True,
        )
    except Exception:
        pass


def apply_auto_live_refresh(section_or_title: object, *, key_prefix: str = "anatole") -> LivePolicy:
    """Installe le rafraîchissement automatique adapté à la section courante.

    Aucun bouton n'est rendu : Anatole applique simplement la cadence pertinente
    selon la section et l'univers actif. Les données restent bornées par les
    délais des fournisseurs publics; ce moteur évite surtout les rechargements
    manuels et renouvelle les caches live au bon rythme.
    """
    policy = live_policy_for(section_or_title)
    now = datetime.now(TORONTO_TZ)
    st.session_state["_anatole_live_section"] = policy.section
    st.session_state["_anatole_live_interval_seconds"] = policy.interval_seconds
    st.session_state["_anatole_live_label"] = policy.label
    st.session_state["_anatole_live_last_seen"] = now.isoformat()

    component_key = f"{key_prefix}_auto_live_{policy.section}_{policy.interval_seconds}"
    if st_autorefresh is not None:
        try:
            count = st_autorefresh(
                interval=int(policy.interval_seconds * 1000),
                limit=None,
                debounce=True,
                key=component_key,
            )
            st.session_state["_anatole_live_refresh_count"] = int(count or 0)
            return policy
        except Exception:
            pass

    # Fallback silencieux si la dépendance n'est pas disponible.
    _inject_meta_refresh(policy.interval_seconds)
    return policy


def live_status_text() -> str:
    label = str(st.session_state.get("_anatole_live_label", "Live"))
    seconds = int(st.session_state.get("_anatole_live_interval_seconds", DEFAULT_INTERVAL_SECONDS) or DEFAULT_INTERVAL_SECONDS)
    return f"{label} · actualisation automatique ~{seconds}s"
