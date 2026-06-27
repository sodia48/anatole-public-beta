from __future__ import annotations

import re
from typing import Any

import streamlit as st


MOBILE_QUERY_KEYS = {"mobile", "m", "__anatole_mobile"}
MOBILE_TRUE_VALUES = {"1", "true", "yes", "oui", "on", "mobile"}
MOBILE_FALSE_VALUES = {"0", "false", "no", "non", "off", "desktop"}
MOBILE_UA_PATTERN = re.compile(
    r"android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile|tablet",
    re.IGNORECASE,
)


def _query_value(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value or default)
    except Exception:
        return default


def _query_bool(name: str) -> bool | None:
    value = _query_value(name, "").strip().lower()
    if not value:
        return None
    if value in MOBILE_TRUE_VALUES:
        return True
    if value in MOBILE_FALSE_VALUES:
        return False
    return None


def _headers_dict() -> dict[str, Any]:
    try:
        context = getattr(st, "context", None)
        if context is None:
            return {}
        headers = getattr(context, "headers", None)
        if headers is None:
            return {}
        if isinstance(headers, dict):
            return headers
        return dict(headers)
    except Exception:
        return {}


def _user_agent() -> str:
    for key, value in _headers_dict().items():
        if str(key).lower() == "user-agent" and value:
            return str(value)
    return ""


def _is_mobile_user_agent(user_agent: str) -> bool:
    return bool(user_agent and MOBILE_UA_PATTERN.search(user_agent))


def bootstrap_mobile_mode() -> None:
    """Détection mobile silencieuse et anti-crash."""
    if st.session_state.get("_mobile_bootstrapped"):
        return

    detected: bool | None = None
    for key in MOBILE_QUERY_KEYS:
        query_value = _query_bool(key)
        if query_value is not None:
            detected = query_value
            break

    if detected is None:
        detected = _is_mobile_user_agent(_user_agent())

    st.session_state["mobile_mode_auto"] = bool(detected)
    st.session_state["_mobile_bootstrapped"] = True


def mobile_mode_enabled() -> bool:
    try:
        bootstrap_mobile_mode()
        return bool(st.session_state.get("mobile_mode_auto", False))
    except Exception:
        return False


def mobile_page_limit(default: int, mobile: int) -> int:
    return mobile if mobile_mode_enabled() else default


def mobile_chart_height(default: int, mobile: int) -> int:
    return mobile if mobile_mode_enabled() else default


def mobile_is_lite() -> bool:
    return mobile_mode_enabled()
