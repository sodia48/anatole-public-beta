from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from core.config import TORONTO_TZ
from core.data import fetch_market_snapshot
from core.utils import extract_ticker_frame, market_status, safe_float


LIVE_QUOTE_REFRESH_SECONDS = 5


def _format_price(value: object, currency: str = "CAD") -> str:
    number = safe_float(value)
    if np.isnan(number):
        return "N/D"
    return f"{number:,.2f} {currency}"


def _format_percent(value: object) -> str:
    number = safe_float(value)
    if np.isnan(number):
        return "N/D"
    return f"{number:+.2f}%"


def _format_volume(value: object) -> str:
    number = safe_float(value)
    if np.isnan(number):
        return "N/D"
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}G"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K"
    return f"{number:,.0f}"


def _local_timestamp(value: object) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value)
    except Exception:
        return None
    try:
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return stamp.tz_convert(TORONTO_TZ)
    except Exception:
        try:
            return stamp.tz_localize(None)
        except Exception:
            return stamp


def _intraday_quote(yahoo_ticker: str) -> dict[str, Any]:
    raw = yf.download(
        tickers=[yahoo_ticker],
        period="5d",
        interval="1m",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=False,
        prepost=False,
        timeout=8,
    )
    frame = extract_ticker_frame(raw, yahoo_ticker)
    if frame is None or frame.empty or "Close" not in frame:
        return {}

    frame = frame.copy()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame = frame.dropna(subset=["Close"])
    if frame.empty:
        return {}

    local_index = []
    for raw_stamp in frame.index:
        stamp = _local_timestamp(raw_stamp)
        local_index.append(stamp if stamp is not None else pd.Timestamp(raw_stamp))
    frame["__LocalTimestamp"] = local_index
    frame["__SessionDate"] = [stamp.date() for stamp in local_index]

    latest_date = frame["__SessionDate"].iloc[-1]
    current_session = frame[frame["__SessionDate"] == latest_date].copy()
    earlier = frame[frame["__SessionDate"] < latest_date].copy()

    current = safe_float(current_session["Close"].iloc[-1])
    previous = safe_float(earlier["Close"].iloc[-1]) if not earlier.empty else np.nan
    change_abs = current - previous if not np.isnan(current) and not np.isnan(previous) else np.nan
    change_pct = (
        change_abs / previous * 100
        if not np.isnan(change_abs) and not np.isnan(previous) and previous != 0
        else np.nan
    )

    high_series = pd.to_numeric(current_session["High"], errors="coerce") if "High" in current_session else pd.Series(dtype=float)
    low_series = pd.to_numeric(current_session["Low"], errors="coerce") if "Low" in current_session else pd.Series(dtype=float)
    volume_series = pd.to_numeric(current_session["Volume"], errors="coerce") if "Volume" in current_session else pd.Series(dtype=float)
    high = safe_float(high_series.max()) if not high_series.empty else np.nan
    low = safe_float(low_series.min()) if not low_series.empty else np.nan
    volume = safe_float(volume_series.sum()) if not volume_series.empty else np.nan
    as_of = current_session["__LocalTimestamp"].iloc[-1]

    spark = current_session[["__LocalTimestamp", "Close"]].tail(120).copy()
    spark.columns = ["Horodatage", "Prix"]

    return {
        "YahooTicker": yahoo_ticker,
        "Prix": current,
        "CloturePrecedente": previous,
        "VariationValeur": change_abs,
        "Variation": change_pct,
        "PlusHaut": high,
        "PlusBas": low,
        "Volume": volume,
        "Horodatage": as_of,
        "SourceCours": "Yahoo Finance · intervalle 1 min",
        "Sparkline": spark,
    }


@st.cache_data(ttl=4, max_entries=128, show_spinner=False)
def fetch_live_quote(yahoo_ticker: str) -> dict[str, Any]:
    """Retourne la dernière cotation disponible pour un seul titre.

    La source publique peut être différée. Le module privilégie l'intraday 1 min,
    puis retombe sur le snapshot Anatole afin de ne jamais casser l'interface.
    """
    ticker = str(yahoo_ticker or "").strip().upper()
    if not ticker:
        return {}

    try:
        quote = _intraday_quote(ticker)
        if quote:
            return quote
    except Exception:
        pass

    try:
        snapshot = fetch_market_snapshot((ticker,))
    except Exception:
        snapshot = pd.DataFrame()
    if snapshot is None or snapshot.empty:
        return {}

    row = snapshot.iloc[0]
    price = safe_float(row.get("Prix"))
    previous = safe_float(row.get("CloturePrecedente"))
    change_abs = price - previous if not np.isnan(price) and not np.isnan(previous) else np.nan
    return {
        "YahooTicker": ticker,
        "Prix": price,
        "CloturePrecedente": previous,
        "VariationValeur": change_abs,
        "Variation": safe_float(row.get("Variation")),
        "PlusHaut": safe_float(row.get("PlusHaut")),
        "PlusBas": safe_float(row.get("PlusBas")),
        "Volume": safe_float(row.get("Volume")),
        "Horodatage": row.get("Horodatage") or datetime.now(TORONTO_TZ),
        "SourceCours": str(row.get("SourceCours") or "Dernière donnée disponible"),
        "Sparkline": pd.DataFrame(),
    }


def remember_live_selection(payload: dict[str, Any]) -> None:
    ticker = str(payload.get("ticker") or payload.get("Ticker") or "").strip()
    yahoo = str(
        payload.get("yahoo")
        or payload.get("YahooTicker")
        or ticker
    ).strip()
    if not ticker and not yahoo:
        return
    st.session_state["anatole_live_selection"] = {
        "ticker": ticker or yahoo,
        "yahoo": yahoo or ticker,
        "name": str(payload.get("name") or payload.get("Nom") or ""),
        "sector": str(payload.get("sector") or payload.get("Secteur") or ""),
    }


def current_live_selection() -> dict[str, str]:
    value = st.session_state.get("anatole_live_selection")
    if isinstance(value, dict):
        return {
            "ticker": str(value.get("ticker") or ""),
            "yahoo": str(value.get("yahoo") or value.get("ticker") or ""),
            "name": str(value.get("name") or ""),
            "sector": str(value.get("sector") or ""),
        }
    ticker = str(st.session_state.get("anatole_bridge_ticker") or "").strip()
    yahoo = str(
        st.session_state.get("anatole_bridge_yahoo")
        or st.session_state.get("selected_ticker")
        or ticker
    ).strip()
    if not ticker and not yahoo:
        return {}
    return {
        "ticker": ticker or yahoo,
        "yahoo": yahoo or ticker,
        "name": str(st.session_state.get("anatole_bridge_name") or ""),
        "sector": str(st.session_state.get("anatole_bridge_sector") or ""),
    }


def _quote_sparkline(quote: dict[str, Any], key: str) -> None:
    spark = quote.get("Sparkline")
    if not isinstance(spark, pd.DataFrame) or spark.empty:
        return
    values = pd.to_numeric(spark.get("Prix"), errors="coerce")
    times = spark.get("Horodatage")
    if values.dropna().empty:
        return
    positive = safe_float(quote.get("Variation")) >= 0
    line_color = "#10B981" if positive else "#EF4444"
    fill_color = "rgba(16,185,129,.10)" if positive else "rgba(239,68,68,.10)"
    fig = go.Figure(
        go.Scatter(
            x=times,
            y=values,
            mode="lines",
            line={"color": line_color, "width": 2.4},
            fill="tozeroy",
            fillcolor=fill_color,
            hovertemplate="%{x|%H:%M}<br>%{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=170,
        margin={"l": 6, "r": 6, "t": 8, "b": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={"visible": False, "fixedrange": True},
        yaxis={"side": "right", "fixedrange": True, "gridcolor": "rgba(148,163,184,.12)"},
    )
    st.plotly_chart(
        fig,
        width="stretch",
        key=key,
        config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
    )


def _render_quote_contents(
    yahoo_ticker: str,
    symbol: str,
    name: str,
    sector: str,
    key_prefix: str,
    compact: bool,
) -> None:
    quote = fetch_live_quote(yahoo_ticker)
    if not quote:
        st.info("La cotation de ce titre est momentanément indisponible.")
        return

    change = safe_float(quote.get("Variation"))
    change_abs = safe_float(quote.get("VariationValeur"))
    direction = "▲" if not np.isnan(change) and change >= 0 else "▼"
    tone = "#10B981" if not np.isnan(change) and change >= 0 else "#EF4444"
    as_of = _local_timestamp(quote.get("Horodatage"))
    time_text = as_of.strftime("%H:%M:%S ET") if as_of is not None else "N/D"
    is_open, _ = market_status()
    status = "Séance en cours" if is_open else "Dernière séance"

    with st.container(border=True):
        top_left, top_right = st.columns([3.2, 1])
        with top_left:
            st.markdown(f"### {symbol or yahoo_ticker} · Cotation live")
            details = " · ".join(item for item in [name, sector] if item)
            if details:
                st.caption(details)
        with top_right:
            st.markdown(
                f"<div style='text-align:right;color:{tone};font-size:1.05rem;font-weight:900'>"
                f"{direction} {_format_percent(change)}</div>",
                unsafe_allow_html=True,
            )
            st.caption(f"{status} · {time_text}")

        metric_cols = st.columns(5 if not compact else 3)
        metric_cols[0].metric(
            "Prix",
            _format_price(quote.get("Prix")),
            None if np.isnan(change_abs) else f"{change_abs:+.2f}",
        )
        metric_cols[1].metric("Variation", _format_percent(change))
        metric_cols[2].metric("Volume", _format_volume(quote.get("Volume")))
        if not compact:
            metric_cols[3].metric("Plus haut", _format_price(quote.get("PlusHaut")))
            metric_cols[4].metric("Plus bas", _format_price(quote.get("PlusBas")))

        _quote_sparkline(quote, key=f"{key_prefix}_{yahoo_ticker}_sparkline")
        st.caption(
            f"Source : {quote.get('SourceCours', 'Dernière donnée disponible')}. "
            "La cotation publique peut être différée selon la place boursière et le fournisseur."
        )


def render_live_quote_panel(
    yahoo_ticker: str,
    *,
    symbol: str = "",
    name: str = "",
    sector: str = "",
    key_prefix: str = "anatole_live_quote",
    compact: bool = False,
    refresh_seconds: int = LIVE_QUOTE_REFRESH_SECONDS,
) -> None:
    """Affiche une cotation qui se renouvelle automatiquement sans bouton."""
    ticker = str(yahoo_ticker or "").strip().upper()
    if not ticker:
        return

    run_every = f"{max(2, int(refresh_seconds))}s"

    try:
        @st.fragment(run_every=run_every)
        def _fragment() -> None:
            _render_quote_contents(
                ticker,
                str(symbol or ticker),
                str(name or ""),
                str(sector or ""),
                key_prefix,
                compact,
            )

        _fragment()
    except Exception:
        _render_quote_contents(
            ticker,
            str(symbol or ticker),
            str(name or ""),
            str(sector or ""),
            key_prefix,
            compact,
        )
