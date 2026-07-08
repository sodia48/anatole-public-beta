from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any

import pandas as pd
import streamlit as st

from core.config import (
    BLACKROCK_HOLDINGS_URL,
    FALLBACK_SECTORS,
    FALLBACK_TICKERS,
)
from core.preferences import save_preferences
from core.utils import raw_to_yahoo


XIC_HOLDINGS_URL = (
    "https://www.blackrock.com/ca/investors/en/products/239837/"
    "ishares-sptsx-capped-composite-index-etf/1464253357814.ajax"
    "?dataType=fund&fileName=XIC_holdings&fileType=csv"
)

XMD_HOLDINGS_URL = (
    "https://www.blackrock.com/ca/investors/en/products/239845/"
    "ishares-sptsx-completion-index-etf/1464253357814.ajax"
    "?dataType=fund&fileName=XMD_holdings&fileType=csv"
)

DEFAULT_UNIVERSE_KEY = "tsx60"


def _env_int(name: str, default: int) -> int:
    try:
        value = int(str(os.getenv(name, "")).strip())
        return value if value > 0 else default
    except Exception:
        return default


def hosting_profile() -> str:
    return str(os.getenv("ANATOLE_HOSTING_PROFILE", "starter")).strip().lower() or "starter"


def default_limits(universe_key: str) -> tuple[int, int]:
    """Retourne (snapshot_limit, history_limit) selon l'hébergement."""
    profile = hosting_profile()
    matrix = {
        "tsx60": {
            "conservative": (70, 60),
            "starter": (60, 45),
            "performance": (70, 70),
        },
        "tsx_composite": {
            "conservative": (100, 60),
            "starter": (100, 50),
            "performance": (240, 140),
        },
        "tsx_full": {
            "conservative": (80, 40),
            "starter": (80, 35),
            "performance": (300, 120),
        },
    }
    limits = matrix.get(universe_key, matrix["tsx60"])
    snapshot, history = limits.get(profile, limits["starter"])
    snapshot = _env_int(f"ANATOLE_{universe_key.upper()}_SNAPSHOT_LIMIT", snapshot)
    history = _env_int(f"ANATOLE_{universe_key.upper()}_HISTORY_LIMIT", history)
    return snapshot, history


@dataclass(frozen=True)
class MarketUniverse:
    key: str
    label: str
    short_label: str
    description: str
    source_kind: str
    expected_count: int | None
    snapshot_limit: int
    history_limit: int
    holdings_urls: tuple[str, ...] = ()
    allow_user_directory: bool = False


UNIVERSES: dict[str, MarketUniverse] = {
    "tsx60": MarketUniverse(
        key="tsx60",
        label="S&P/TSX 60",
        short_label="TSX 60",
        description="Grandes capitalisations canadiennes. Mode le plus rapide.",
        source_kind="blackrock_xiu",
        expected_count=60,
        snapshot_limit=default_limits("tsx60")[0],
        history_limit=default_limits("tsx60")[1],
        holdings_urls=(BLACKROCK_HOLDINGS_URL,),
    ),
    "tsx_composite": MarketUniverse(
        key="tsx_composite",
        label="S&P/TSX Composite",
        short_label="Composite",
        description=(
            "Univers canadien large via XIC. Plus riche que le TSX 60, "
            "mais encore assez rapide."
        ),
        source_kind="blackrock_xic",
        expected_count=None,
        snapshot_limit=default_limits("tsx_composite")[0],
        history_limit=default_limits("tsx_composite")[1],
        holdings_urls=(XIC_HOLDINGS_URL,),
    ),
    "tsx_full": MarketUniverse(
        key="tsx_full",
        label="TSX complet / étendu",
        short_label="TSX étendu",
        description=(
            "Univers TSX élargi avec couverture progressive des titres canadiens, "
            "incluant un proxy large lorsque la source complète est temporairement limitée."
        ),
        source_kind="tsx_directory_or_proxy",
        expected_count=None,
        snapshot_limit=default_limits("tsx_full")[0],
        history_limit=default_limits("tsx_full")[1],
        holdings_urls=(XIC_HOLDINGS_URL, XMD_HOLDINGS_URL),
        allow_user_directory=True,
    ),
}


# Graine de secours élargie. Elle n'est utilisée que si les sources live échouent.
TSX_EXTENDED_SEED = sorted(set(FALLBACK_TICKERS + [
    "AC", "ACO.X", "ADEN", "AIF", "ALA", "AP.UN", "AQN", "ARE", "ARX", "ATS",
    "BBD.B", "BEP.UN", "BIP.UN", "BLX", "BNE", "BTE", "CAR.UN", "CCA", "CCL.B",
    "CFP", "CG", "CJT", "CJT", "CS", "CSH.UN", "CU", "DPM", "DRM", "DSG",
    "D.UN", "EFN", "ELD", "EMP.A", "EQB", "ERO", "EIF", "EXE", "FCR.UN",
    "FIL", "FRU", "FSZ", "GFL", "GOOS", "GRT.UN", "GSY", "HBM", "HR.UN",
    "HWX", "IAG", "IGM", "IPL", "IVN", "KEY", "KMP.UN", "KXS", "LB", "LIF",
    "LSPD", "MATR", "MEG", "MTL", "MX", "NFI", "NG", "NPI", "NVA", "OLA",
    "OR", "PAAS", "PBH", "PEY", "PKI", "POU", "PSK", "PXT", "REAL", "REI.UN",
    "RUS", "SIA", "SJ", "SOBO", "SOT.UN", "SPB", "SSRM", "STN", "TFII",
    "TIH", "TIXT", "TNT.UN", "TPZ", "TXG", "U.UN", "UNS", "VET", "VGP",
    "WDO", "WEED", "WFG", "X", "YRI",
]))


def universe_keys() -> list[str]:
    return list(UNIVERSES)


def get_universe(key: str | None = None) -> MarketUniverse:
    return UNIVERSES.get(str(key or DEFAULT_UNIVERSE_KEY), UNIVERSES[DEFAULT_UNIVERSE_KEY])


def _query_value(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value or default)
    except Exception:
        return default


def current_universe_key() -> str:
    session_value = st.session_state.get("market_universe")
    if session_value in UNIVERSES:
        return str(session_value)

    query_value = _query_value("universe")
    if query_value in UNIVERSES:
        st.session_state["market_universe"] = query_value
        return query_value

    st.session_state["market_universe"] = DEFAULT_UNIVERSE_KEY
    return DEFAULT_UNIVERSE_KEY


def current_universe() -> MarketUniverse:
    return get_universe(current_universe_key())


def set_current_universe(key: str) -> None:
    safe_key = key if key in UNIVERSES else DEFAULT_UNIVERSE_KEY
    previous = st.session_state.get("market_universe")
    st.session_state["market_universe"] = safe_key
    st.session_state["_market_universe_nonce"] = int(st.session_state.get("_market_universe_nonce", 0) or 0) + 1
    try:
        st.query_params["universe"] = safe_key
    except Exception:
        pass
    if previous != safe_key:
        # Drop page-local derived state that can make the UI look like the old universe.
        for key_name in [
            "_perf_cockpit",
            "_perf_screener",
            "_perf_actualites",
            "_perf_focus_history",
        ]:
            st.session_state.pop(key_name, None)


def render_universe_selector(profile: str) -> str:
    """Affiche le sélecteur d'univers dans la barre latérale."""
    keys = universe_keys()
    current_key = current_universe_key()
    selected = st.sidebar.selectbox(
        "Univers de marché",
        keys,
        index=keys.index(current_key),
        format_func=lambda value: UNIVERSES[value].label,
        help=(
            "TSX 60 reste le mode le plus rapide. Composite et TSX étendu "
            "chargent plus de titres avec des limites intelligentes."
        ),
        key=f"market_universe_selector_{current_key}",
    )

    if selected != current_key:
        set_current_universe(selected)
        save_preferences(profile, {"market_universe": selected})
        try:
            from core.runtime import clear_universe_caches

            clear_universe_caches()
        except Exception:
            pass
        st.rerun()

    universe = get_universe(selected)
    st.sidebar.caption(universe.description)
    return selected


def render_universe_selector_inline(profile: str, key_suffix: str = "main") -> str:
    """Sélecteur d'univers accessible hors barre latérale.

    Utile surtout sur mobile, où la sidebar est masquée pour préserver l'espace.
    Le choix reste synchronisé avec st.session_state et les paramètres d'URL.
    """
    keys = universe_keys()
    current_key = current_universe_key()

    labels = {
        "tsx60": "TSX 60",
        "tsx_composite": "Composite",
        "tsx_full": "TSX étendu",
    }

    selected = st.radio(
        "Univers de marché",
        keys,
        index=keys.index(current_key),
        format_func=lambda value: labels.get(value, UNIVERSES[value].short_label),
        horizontal=True,
        key=f"market_universe_inline_{key_suffix}_{current_key}",
        help=(
            "TSX 60 est le plus rapide. Composite élargit la couverture. "
            "TSX étendu charge davantage de titres avec des limites de performance."
        ),
    )

    if selected != current_key:
        set_current_universe(selected)
        save_preferences(profile, {"market_universe": selected})
        try:
            from core.runtime import clear_universe_caches

            clear_universe_caches()
        except Exception:
            pass
        st.rerun()

    return selected



def normalise_tmx_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    raw = raw.replace(":TSX", "").replace(":XTSE", "").replace(".TO", "")
    raw = raw.replace("/", ".").replace("-", ".")
    raw = re.sub(r"\s+", "", raw)
    return raw


def seed_constituents(universe_key: str) -> pd.DataFrame:
    universe = get_universe(universe_key)
    if universe_key == "tsx60":
        symbols = FALLBACK_TICKERS
        source = "Liste de secours TSX 60 intégrée"
    else:
        symbols = TSX_EXTENDED_SEED
        source = "Liste de secours TSX élargie intégrée"

    equal_weight = 100 / max(len(symbols), 1)
    return pd.DataFrame(
        [
            {
                "Ticker": symbol,
                "Nom": symbol,
                "Secteur": FALLBACK_SECTORS.get(symbol, "Autre"),
                "PoidsIndice": equal_weight,
                "YahooTicker": raw_to_yahoo(symbol),
                "SourceComposition": source,
                "Univers": universe.short_label,
            }
            for symbol in symbols
        ]
    )


def user_directory_paths() -> list[str]:
    configured = os.getenv("ANATOLE_TMX_ISSUERS_URL", "").strip()
    local_default = str((__import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "tsx_universe.csv"))
    return [value for value in (configured, local_default) if value]
