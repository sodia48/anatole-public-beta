from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from core.config import (
    BLACKROCK_HOLDINGS_URL,
    EXPECTED_CONSTITUENTS,
    FALLBACK_SECTORS,
    FALLBACK_TICKERS,
    TORONTO_TZ,
)
from core.utils import extract_ticker_frame, market_status, parse_timestamp, raw_to_yahoo, safe_float


def fallback_constituents() -> pd.DataFrame:
    equal_weight = 100 / len(FALLBACK_TICKERS)
    return pd.DataFrame(
        [
            {
                "Ticker": ticker,
                "Nom": ticker,
                "Secteur": FALLBACK_SECTORS.get(ticker, "Autre"),
                "PoidsIndice": equal_weight,
                "YahooTicker": raw_to_yahoo(ticker),
                "SourceComposition": "Liste de secours intégrée",
            }
            for ticker in FALLBACK_TICKERS
        ]
    )


@st.cache_data(ttl=43_200, show_spinner=False)
def load_constituents() -> tuple[pd.DataFrame, dict[str, Any]]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
    }
    diagnostics: dict[str, Any] = {
        "expected": EXPECTED_CONSTITUENTS,
        "source": "Positions XIU",
        "downloaded_at": datetime.now(TORONTO_TZ).isoformat(),
        "error": "",
    }

    try:
        response = requests.get(BLACKROCK_HOLDINGS_URL, headers=headers, timeout=25)
        response.raise_for_status()
        lines = response.text.splitlines()
        header_index = next(
            index
            for index, line in enumerate(lines)
            if "Ticker" in line and "Name" in line and "Sector" in line
        )
        holdings = pd.read_csv(StringIO("\n".join(lines[header_index:])))
        holdings.columns = [str(column).strip() for column in holdings.columns]
        required = {"Ticker", "Name", "Sector"}
        if not required.issubset(holdings.columns):
            raise ValueError("Colonnes attendues absentes du fichier XIU.")

        holdings["Ticker"] = holdings["Ticker"].astype(str).str.strip().str.upper()
        valid_ticker = holdings["Ticker"].str.match(r"^[A-Z]{1,6}(?:\.[A-Z]{1,3})?$")
        holdings = holdings.loc[valid_ticker].copy()

        if "Asset Class" in holdings.columns:
            holdings = holdings[
                holdings["Asset Class"].astype(str).str.contains(
                    "Equity", case=False, na=False
                )
            ]

        duplicate_symbols = sorted(
            holdings.loc[holdings["Ticker"].duplicated(keep=False), "Ticker"]
            .dropna()
            .unique()
            .tolist()
        )
        holdings = holdings.drop_duplicates(subset=["Ticker"], keep="first")

        weight_column = next(
            (column for column in holdings.columns if "weight" in column.lower()),
            None,
        )
        if weight_column:
            holdings["PoidsIndice"] = pd.to_numeric(
                holdings[weight_column], errors="coerce"
            )
        else:
            holdings["PoidsIndice"] = 100 / max(len(holdings), 1)

        holdings["PoidsIndice"] = holdings["PoidsIndice"].fillna(
            100 / max(len(holdings), 1)
        )
        holdings["Nom"] = holdings["Name"].fillna(holdings["Ticker"]).astype(str)
        holdings["Secteur"] = (
            holdings["Sector"].fillna("Autre").replace({"": "Autre"}).astype(str)
        )
        holdings["YahooTicker"] = holdings["Ticker"].map(raw_to_yahoo)
        holdings["SourceComposition"] = "Positions XIU téléchargées"

        result = holdings[
            [
                "Ticker",
                "Nom",
                "Secteur",
                "PoidsIndice",
                "YahooTicker",
                "SourceComposition",
            ]
        ].copy()
        result = result.sort_values("PoidsIndice", ascending=False).head(EXPECTED_CONSTITUENTS)
        result = result.reset_index(drop=True)

        fallback_set = set(FALLBACK_TICKERS)
        live_set = set(result["Ticker"])
        diagnostics.update(
            {
                "actual": len(result),
                "duplicates": duplicate_symbols,
                "missing_vs_fallback": sorted(fallback_set - live_set),
                "new_vs_fallback": sorted(live_set - fallback_set),
                "status": "OK" if len(result) == EXPECTED_CONSTITUENTS else "À vérifier",
            }
        )
        if len(result) < 50:
            raise ValueError("Nombre anormalement faible de constituants.")
        return result, diagnostics

    except Exception as exc:
        result = fallback_constituents()
        diagnostics.update(
            {
                "actual": len(result),
                "duplicates": [],
                "missing_vs_fallback": [],
                "new_vs_fallback": [],
                "status": "Liste de secours",
                "source": "Liste de secours intégrée",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return result, diagnostics


@st.cache_data(ttl=60, show_spinner=False)
def fetch_market_snapshot(tickers: tuple[str, ...]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    daily = yf.download(
        tickers=list(tickers),
        period="8d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        prepost=False,
    )
    is_open, _ = market_status()
    # Hors séance, les barres intrajournalières n'apportent pas de valeur fraîche
    # et ralentissent fortement le premier chargement.
    if is_open:
        intraday = yf.download(
            tickers=list(tickers),
            period="1d",
            interval="5m",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
            prepost=False,
        )
    else:
        intraday = pd.DataFrame()
    rows: list[dict[str, Any]] = []

    for ticker in tickers:
        daily_frame = extract_ticker_frame(daily, ticker)
        intraday_frame = extract_ticker_frame(intraday, ticker)
        daily_close = (
            pd.to_numeric(daily_frame.get("Close"), errors="coerce").dropna()
            if "Close" in daily_frame
            else pd.Series(dtype=float)
        )
        intraday_close = (
            pd.to_numeric(intraday_frame.get("Close"), errors="coerce").dropna()
            if "Close" in intraday_frame
            else pd.Series(dtype=float)
        )
        if daily_close.empty and intraday_close.empty:
            continue

        current = float(intraday_close.iloc[-1]) if not intraday_close.empty else float(daily_close.iloc[-1])
        # La variation est toujours calculée contre la séance précédente.
        # Le dernier bar quotidien peut représenter la séance courante ou la dernière séance close.
        previous = float(daily_close.iloc[-2]) if len(daily_close) >= 2 else np.nan

        variation = ((current - previous) / previous) * 100 if previous else np.nan
        high = (
            safe_float(pd.to_numeric(intraday_frame.get("High"), errors="coerce").max())
            if not intraday_frame.empty and "High" in intraday_frame
            else safe_float(daily_frame["High"].iloc[-1])
            if not daily_frame.empty and "High" in daily_frame
            else np.nan
        )
        low = (
            safe_float(pd.to_numeric(intraday_frame.get("Low"), errors="coerce").min())
            if not intraday_frame.empty and "Low" in intraday_frame
            else safe_float(daily_frame["Low"].iloc[-1])
            if not daily_frame.empty and "Low" in daily_frame
            else np.nan
        )
        volume = (
            safe_float(pd.to_numeric(intraday_frame.get("Volume"), errors="coerce").sum())
            if not intraday_frame.empty and "Volume" in intraday_frame
            else safe_float(daily_frame["Volume"].iloc[-1])
            if not daily_frame.empty and "Volume" in daily_frame
            else np.nan
        )
        rows.append(
            {
                "YahooTicker": ticker,
                "Prix": current,
                "CloturePrecedente": previous,
                "Variation": variation,
                "PlusHaut": high,
                "PlusBas": low,
                "Volume": volume,
                "Horodatage": datetime.now(TORONTO_TZ),
                "SourceCours": "Yahoo Finance",
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=1_800, show_spinner=False)
def fetch_batch_history(
    tickers: tuple[str, ...], period: str = "1y", interval: str = "1d"
) -> dict[str, pd.DataFrame]:
    if not tickers:
        return {}
    data = yf.download(
        tickers=list(tickers),
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        prepost=False,
    )
    return {ticker: extract_ticker_frame(data, ticker) for ticker in tickers}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    data = yf.download(
        tickers=ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        prepost=False,
        threads=True,
    )
    return extract_ticker_frame(data, ticker)


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_company_info(ticker: str) -> dict[str, Any]:
    try:
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _one_fundamental(ticker: str) -> dict[str, Any]:
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    dividend = safe_float(info.get("dividendYield"))
    return {
        "YahooTicker": ticker,
        "MarketCap": safe_float(info.get("marketCap")),
        "PE": safe_float(info.get("trailingPE")),
        "ForwardPE": safe_float(info.get("forwardPE")),
        "DividendYield": dividend * 100 if not np.isnan(dividend) else np.nan,
        "Beta": safe_float(info.get("beta")),
        "ProfitMargin": safe_float(info.get("profitMargins")) * 100,
        "RevenueGrowth": safe_float(info.get("revenueGrowth")) * 100,
        "DebtToEquity": safe_float(info.get("debtToEquity")),
        "TargetMeanPrice": safe_float(info.get("targetMeanPrice")),
        "Currency": info.get("currency", "CAD"),
    }


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_fundamentals(tickers: tuple[str, ...]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_one_fundamental, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            try:
                rows.append(future.result())
            except Exception:
                rows.append({"YahooTicker": futures[future]})
    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock_news(ticker: str) -> list[dict[str, str]]:
    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception:
        return []
    articles: list[dict[str, str]] = []
    for item in raw_news:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        source = content if isinstance(content, dict) else item
        provider_value = source.get("provider")
        if isinstance(provider_value, dict):
            publisher = provider_value.get("displayName", "")
        else:
            publisher = item.get("publisher", "") or str(provider_value or "")
        canonical_url = source.get("canonicalUrl")
        click_url = source.get("clickThroughUrl")
        url = ""
        if isinstance(canonical_url, dict):
            url = canonical_url.get("url", "")
        if not url and isinstance(click_url, dict):
            url = click_url.get("url", "")
        if not url:
            url = item.get("link", "")
        title = source.get("title") or item.get("title") or "Sans titre"
        summary = source.get("summary") or item.get("summary") or ""
        published = source.get("pubDate") or source.get("displayTime") or item.get("providerPublishTime")
        timestamp = parse_timestamp(published)
        articles.append(
            {
                "Ticker": ticker,
                "Titre": str(title),
                "URL": str(url),
                "Source": str(publisher),
                "Resume": str(summary),
                "Date": timestamp.isoformat() if timestamp is not None else "",
            }
        )
    return articles


@st.cache_data(ttl=3_600, show_spinner=False)
def fetch_calendar_bundle(ticker: str) -> dict[str, Any]:
    stock = yf.Ticker(ticker)
    result: dict[str, Any] = {"ticker": ticker, "calendar": {}, "earnings": [], "dividends": [], "splits": [], "key_dates": []}
    try:
        calendar = stock.calendar
        if isinstance(calendar, pd.DataFrame):
            if not calendar.empty:
                if calendar.shape[1] == 1:
                    result["calendar"] = calendar.iloc[:, 0].to_dict()
                else:
                    result["calendar"] = calendar.to_dict()
        elif isinstance(calendar, dict):
            result["calendar"] = calendar
    except Exception:
        pass
    try:
        earnings = stock.get_earnings_dates(limit=12)
        if isinstance(earnings, pd.DataFrame) and not earnings.empty:
            temp = earnings.reset_index()
            temp.columns = [str(col) for col in temp.columns]
            result["earnings"] = temp.to_dict(orient="records")
    except Exception:
        pass
    try:
        info = stock.info or {}
        for field, label in [("exDividendDate", "Date ex-dividende"), ("dividendDate", "Paiement du dividende")]:
            timestamp = parse_timestamp(info.get(field))
            if timestamp is not None:
                result["key_dates"].append({"Date": timestamp.isoformat(), "Evenement": label, "Detail": info.get("dividendRate", "")})
    except Exception:
        pass
    try:
        dividends = stock.dividends
        if isinstance(dividends, pd.Series) and not dividends.empty:
            recent = dividends.tail(8).reset_index()
            recent.columns = ["Date", "Dividende"]
            result["dividends"] = recent.to_dict(orient="records")
    except Exception:
        pass
    try:
        splits = stock.splits
        if isinstance(splits, pd.Series) and not splits.empty:
            recent_splits = splits.tail(8).reset_index()
            recent_splits.columns = ["Date", "Ratio"]
            result["splits"] = recent_splits.to_dict(orient="records")
    except Exception:
        pass
    return result


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_dividend_history(ticker: str, period: str = "10y") -> pd.DataFrame:
    try:
        history = yf.Ticker(ticker).history(period=period, actions=True, auto_adjust=False)
        if history.empty or "Dividends" not in history:
            return pd.DataFrame(columns=["Date", "Dividende"])
        dividends = history.loc[history["Dividends"] > 0, ["Dividends"]].reset_index()
        date_column = dividends.columns[0]
        dividends = dividends.rename(columns={date_column: "Date", "Dividends": "Dividende"})
        return dividends[["Date", "Dividende"]]
    except Exception:
        return pd.DataFrame(columns=["Date", "Dividende"])


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_recommendation_summary(ticker: str) -> pd.DataFrame:
    try:
        frame = yf.Ticker(ticker).recommendations_summary
        return frame.reset_index(drop=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_insider_transactions(ticker: str) -> pd.DataFrame:
    try:
        frame = yf.Ticker(ticker).insider_transactions
        return frame.reset_index(drop=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=15, show_spinner=False)
def fetch_twelve_data_quotes(
    raw_tickers: tuple[str, ...], api_key: str
) -> tuple[dict[str, dict[str, float]], list[str]]:
    if not api_key or not raw_tickers:
        return {}, []
    quotes: dict[str, dict[str, float]] = {}
    errors: list[str] = []
    for start in range(0, len(raw_tickers), 8):
        chunk = raw_tickers[start : start + 8]
        symbols = [f"{ticker}:TSX" for ticker in chunk]
        try:
            response = requests.get(
                "https://api.twelvedata.com/quote",
                params={"symbol": ",".join(symbols), "apikey": api_key},
                timeout=25,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("status") == "error":
                errors.append(str(payload.get("message", "Erreur API")))
                continue
            if len(symbols) == 1 and isinstance(payload, dict) and "symbol" in payload:
                payload = {symbols[0]: payload}
            for raw, requested in zip(chunk, symbols):
                item = payload.get(requested) or payload.get(raw) if isinstance(payload, dict) else None
                if not isinstance(item, dict):
                    continue
                quotes[raw] = {
                    "Prix": safe_float(item.get("close")),
                    "CloturePrecedente": safe_float(item.get("previous_close")),
                    "Variation": safe_float(item.get("percent_change")),
                    "PlusHaut": safe_float(item.get("high")),
                    "PlusBas": safe_float(item.get("low")),
                    "Volume": safe_float(item.get("volume")),
                }
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    return quotes, errors
