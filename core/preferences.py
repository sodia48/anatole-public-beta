from __future__ import annotations

from typing import Any

import streamlit as st

from core.database import get_preferences, set_preferences


DEFAULT_PREFERENCES: dict[str, str] = {
    "theme": "dark",
    "density": "comfortable",
    "experience_mode": "simple",
    "show_ticker": "true",
    "show_quick_links": "true",
    "show_animations": "true",
    "show_advanced_home": "false",
    "show_mobile_nav": "true",
    "default_period": "1y",
    "decimal_places": "2",
    "refresh_seconds": "60",
    "refresh_only_market_open": "true",
    "show_event_markers": "false",
    "market_universe": "tsx60",
}


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "oui", "on"}


def as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_preferences(profile: str) -> dict[str, str]:
    stored = get_preferences(profile)
    return {
        key: stored.get(key, default)
        for key, default in DEFAULT_PREFERENCES.items()
    }


def hydrate_preferences(profile: str) -> bool:
    """Charge les préférences dans la session. Retourne True si une relance est utile."""
    if st.session_state.get("_preferences_profile") == profile:
        return False

    prefs = load_preferences(profile)
    mapping = {
        "theme_toggle": as_bool(prefs["theme"] == "dark"),
        "compact_toggle": prefs["density"] == "compact",
        "experience_mode": prefs["experience_mode"],
        "show_ticker": as_bool(prefs["show_ticker"]),
        "show_quick_links": as_bool(prefs["show_quick_links"]),
        "show_animations": as_bool(prefs["show_animations"]),
        "show_advanced_home": as_bool(prefs["show_advanced_home"]),
        "show_mobile_nav": as_bool(prefs["show_mobile_nav"], True),
        "default_period": prefs["default_period"],
        "decimal_places": as_int(prefs["decimal_places"], 2),
        "refresh_seconds": as_int(prefs["refresh_seconds"], 60),
        "refresh_only_market_open": as_bool(prefs["refresh_only_market_open"], True),
        "show_event_markers": as_bool(prefs["show_event_markers"]),
        "market_universe": prefs.get("market_universe", "tsx60"),
    }

    changed = False
    for key, value in mapping.items():
        if st.session_state.get(key) != value:
            st.session_state[key] = value
            changed = True

    st.session_state["_preferences_profile"] = profile
    return changed


def save_preferences(profile: str, values: dict[str, Any]) -> None:
    payload: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, bool):
            payload[key] = "true" if value else "false"
        else:
            payload[key] = str(value)
    set_preferences(profile, payload)


def session_preference(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)
