from __future__ import annotations

import streamlit as st


MOBILE_QUERY_KEYS = {"mobile", "m"}


def _query_value(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value or default)
    except Exception:
        return default


def mobile_mode_enabled() -> bool:
    """Mode mobile volontairement simple et robuste.

    Streamlit ne donne pas toujours accès au user-agent côté serveur.
    Anatole combine donc :
    - une préférence de session ;
    - un query param pratique pour testeurs : ?mobile=1 ;
    - du CSS responsive dans core/ui.py.
    """
    query_mobile = any(_query_value(key).lower() in {"1", "true", "yes", "oui", "on"} for key in MOBILE_QUERY_KEYS)
    return bool(st.session_state.get("mobile_mode", False) or query_mobile)


def render_mobile_mode_toggle() -> None:
    """Petit contrôle discret pour testeurs mobiles."""
    current = mobile_mode_enabled()
    enabled = st.toggle(
        "Mode mobile allégé",
        value=current,
        help="Réduit les blocs lourds et privilégie les sections essentielles sur téléphone.",
        key="mobile_mode",
    )
    if enabled and not current:
        st.rerun()


def mobile_page_limit(default: int, mobile: int) -> int:
    return mobile if mobile_mode_enabled() else default


def mobile_chart_height(default: int, mobile: int) -> int:
    return mobile if mobile_mode_enabled() else default


def mobile_is_lite() -> bool:
    return mobile_mode_enabled()
