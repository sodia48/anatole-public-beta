from __future__ import annotations

import re
from typing import Any

import streamlit as st
import streamlit.components.v1 as components


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
        headers = getattr(st.context, "headers", None)
        if headers is None:
            return {}
        if isinstance(headers, dict):
            return headers
        return dict(headers)
    except Exception:
        return {}


def _user_agent() -> str:
    headers = _headers_dict()
    for key in ("user-agent", "User-Agent", "USER-AGENT"):
        value = headers.get(key)
        if value:
            return str(value)
    return ""


def _is_mobile_user_agent(user_agent: str) -> bool:
    return bool(user_agent and MOBILE_UA_PATTERN.search(user_agent))


def _inject_mobile_probe() -> None:
    """Fallback discret côté navigateur.

    Si Streamlit ne donne pas le user-agent côté serveur, ce script ajoute
    un paramètre technique une seule fois. Aucun message ni contrôle visible
    n'est affiché à l'utilisateur.
    """
    components.html(
        """
        <script>
        (function() {
          try {
            const url = new URL(window.parent.location.href);
            const hasManual = url.searchParams.has('mobile') || url.searchParams.has('m');
            const hasAuto = url.searchParams.has('__anatole_mobile');
            if (hasManual || hasAuto) return;

            const ua = navigator.userAgent || navigator.vendor || window.opera || '';
            const isMobileUA = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile|tablet/i.test(ua);
            const width = Math.min(window.parent.innerWidth || 1400, screen.width || 1400);
            const detected = (isMobileUA || width <= 1024) ? '1' : '0';

            url.searchParams.set('__anatole_mobile', detected);
            window.parent.location.replace(url.toString());
          } catch (error) {}
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def bootstrap_mobile_mode() -> None:
    if st.session_state.get("_mobile_bootstrapped"):
        return

    for key in MOBILE_QUERY_KEYS:
        query_value = _query_bool(key)
        if query_value is not None:
            st.session_state["mobile_mode_auto"] = query_value
            st.session_state["_mobile_bootstrapped"] = True
            return

    user_agent = _user_agent()
    if user_agent:
        st.session_state["mobile_mode_auto"] = _is_mobile_user_agent(user_agent)
        st.session_state["_mobile_bootstrapped"] = True
        return

    # Client-side fallback. The rerun will set __anatole_mobile.
    _inject_mobile_probe()
    st.session_state["mobile_mode_auto"] = False
    st.session_state["_mobile_bootstrapped"] = True


def mobile_mode_enabled() -> bool:
    bootstrap_mobile_mode()
    return bool(st.session_state.get("mobile_mode_auto", False))


def mobile_page_limit(default: int, mobile: int) -> int:
    return mobile if mobile_mode_enabled() else default


def mobile_chart_height(default: int, mobile: int) -> int:
    return mobile if mobile_mode_enabled() else default


def mobile_is_lite() -> bool:
    return mobile_mode_enabled()
