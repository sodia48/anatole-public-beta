from __future__ import annotations

import math
import os
from datetime import datetime, time
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from core.config import TORONTO_TZ


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
        if value not in (None, ""):
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


def safe_float(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def format_number(value: Any, decimals: int = 2) -> str:
    number = safe_float(value)
    if np.isnan(number):
        return "N/D"
    return f"{number:,.{decimals}f}"


def format_money(value: Any, currency: str = "CAD") -> str:
    number = safe_float(value)
    if np.isnan(number):
        return "N/D"
    symbol = "$" if currency in {"CAD", "USD"} else f"{currency} "
    return f"{symbol}{number:,.2f}"


def format_compact(value: Any) -> str:
    number = safe_float(value)
    if np.isnan(number):
        return "N/D"
    absolute = abs(number)
    if absolute >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:.2f} T"
    if absolute >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f} G"
    if absolute >= 1_000_000:
        return f"{number / 1_000_000:.2f} M"
    if absolute >= 1_000:
        return f"{number / 1_000:.2f} k"
    return f"{number:,.0f}"


def raw_to_yahoo(raw_ticker: str) -> str:
    raw = str(raw_ticker).strip().upper()
    if raw.endswith(".TO"):
        return raw
    return raw.replace(".", "-") + ".TO"


def yahoo_to_raw(ticker: str) -> str:
    ticker = ticker.strip().upper()
    if ticker.endswith(".TO"):
        return ticker[:-3].replace("-", ".")
    return ticker


def normalise_symbol(symbol: str, constituents: pd.DataFrame | None = None) -> str:
    symbol = str(symbol).strip().upper()
    if not symbol:
        return ""

    if constituents is not None and not constituents.empty:
        raw_map = dict(zip(constituents["Ticker"], constituents["YahooTicker"]))
        if symbol in raw_map:
            return raw_map[symbol]
        if symbol in set(constituents["YahooTicker"]):
            return symbol

    if symbol.endswith(":TSX"):
        return raw_to_yahoo(symbol.removesuffix(":TSX"))
    if symbol.endswith(".TO"):
        return symbol
    if "." in symbol and symbol.split(".")[-1] in {"A", "B", "UN"}:
        return raw_to_yahoo(symbol)
    return symbol


def market_status() -> tuple[bool, str]:
    now = datetime.now(TORONTO_TZ)
    is_weekday = now.weekday() < 5
    is_open = is_weekday and time(9, 30) <= now.time() <= time(16, 0)
    label = "Marché probablement ouvert" if is_open else "Marché probablement fermé"
    return is_open, f"{label} · {now:%H:%M:%S} ET"


def extract_ticker_frame(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    frame = data.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        for level in range(frame.columns.nlevels):
            values = frame.columns.get_level_values(level)
            if ticker in values:
                result = frame.xs(ticker, axis=1, level=level, drop_level=True)
                if isinstance(result, pd.Series):
                    result = result.to_frame()
                return result.dropna(how="all")
        return pd.DataFrame()
    frame.columns = [str(col) for col in frame.columns]
    return frame.dropna(how="all")


def parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return pd.Timestamp(value, unit="s", tz="UTC")
        return pd.to_datetime(value, utc=True)
    except Exception:
        return None


def dataframe_json(df: pd.DataFrame) -> str:
    return df.to_json(orient="records", date_format="iso")
