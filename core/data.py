from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from datetime import datetime
from io import StringIO
from pathlib import Path
import os
import re
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
from core.universe import current_universe_key, get_universe, seed_constituents, normalise_tmx_symbol
from core.fundamental_fallback import (
    fetch_tradingview_fundamentals,
    merge_tradingview_into_info,
)
from core.utils import (
    extract_ticker_frame,
    market_status,
    parse_timestamp,
    raw_to_yahoo,
    safe_float,
)


@st.cache_resource
def _market_snapshot_store() -> dict[str, Any]:
    return {"frames": {}, "updated_at": None}


def _snapshot_key(tickers: tuple[str, ...]) -> str:
    return "|".join(sorted(str(ticker) for ticker in tickers))


def _env_flag(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on", "oui"}


def _env_positive_int(name: str, default: int) -> int:
    try:
        value = int(str(os.getenv(name, "")).strip())
        return value if value > 0 else default
    except Exception:
        return default


def _use_intraday_snapshot(ticker_count: int) -> bool:
    mode = str(os.getenv("ANATOLE_INTRADAY_QUOTES", "auto")).strip().lower()
    if mode in {"1", "true", "yes", "on", "force", "always", "oui"}:
        return True
    if mode in {"0", "false", "no", "off", "never", "non"}:
        return False

    # Le 5 minutes est utile sur un petit univers, mais devient le principal
    # ralentisseur sur Composite/TSX etendu. Le seuil reste configurable.
    limit = _env_positive_int("ANATOLE_INTRADAY_MAX_TICKERS", 70)
    return ticker_count <= limit


def _last_good_snapshot(tickers: tuple[str, ...] | None = None) -> pd.DataFrame:
    store = _market_snapshot_store()
    frames = store.get("frames", {})
    if not isinstance(frames, dict):
        return pd.DataFrame()

    if tickers:
        key = _snapshot_key(tickers)
        frame = frames.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            result = frame.copy()
            result["SourceCours"] = "Dernière donnée disponible"
            return result

        # Fallback strict : only keep rows matching the requested tickers.
        wanted = set(tickers)
        collected = []
        for candidate in frames.values():
            if isinstance(candidate, pd.DataFrame) and not candidate.empty and "YahooTicker" in candidate:
                filtered = candidate[candidate["YahooTicker"].isin(wanted)].copy()
                if not filtered.empty:
                    collected.append(filtered)

        if collected:
            result = pd.concat(collected, ignore_index=True)
            result = result.drop_duplicates(subset=["YahooTicker"], keep="last")
            result["SourceCours"] = "Dernière donnée disponible"
            return result

        return pd.DataFrame()

    latest = None
    for candidate in frames.values():
        if isinstance(candidate, pd.DataFrame) and not candidate.empty:
            latest = candidate
    if latest is None:
        return pd.DataFrame()
    result = latest.copy()
    result["SourceCours"] = "Dernière donnée disponible"
    return result


def _download_blackrock_holdings(url: str, universe_key: str) -> pd.DataFrame:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/149 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=8)
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
        raise ValueError("Colonnes attendues absentes du fichier BlackRock.")

    holdings["Ticker"] = holdings["Ticker"].astype(str).str.strip().str.upper()
    holdings = holdings[
        holdings["Ticker"].str.match(r"^[A-Z0-9]{1,8}(?:[.-][A-Z0-9]{1,4})?$", na=False)
    ].copy()

    if "Asset Class" in holdings.columns:
        holdings = holdings[
            holdings["Asset Class"].astype(str).str.contains(
                "Equity", case=False, na=False
            )
        ]

    weight_column = next(
        (column for column in holdings.columns if "weight" in column.lower()),
        None,
    )
    if weight_column:
        holdings["PoidsIndice"] = pd.to_numeric(
            holdings[weight_column], errors="coerce"
        )
    else:
        holdings["PoidsIndice"] = np.nan

    holdings["Ticker"] = holdings["Ticker"].str.replace("-", ".", regex=False)
    holdings["Nom"] = holdings["Name"].fillna(holdings["Ticker"]).astype(str)
    holdings["Secteur"] = (
        holdings["Sector"].fillna("Autre").replace({"": "Autre"}).astype(str)
    )
    holdings["YahooTicker"] = holdings["Ticker"].map(raw_to_yahoo)
    holdings["SourceComposition"] = "Positions BlackRock téléchargées"
    holdings["Univers"] = get_universe(universe_key).short_label

    return holdings[
        [
            "Ticker",
            "Nom",
            "Secteur",
            "PoidsIndice",
            "YahooTicker",
            "SourceComposition",
            "Univers",
        ]
    ].copy()


def _load_user_tsx_directory(universe_key: str) -> pd.DataFrame:
    """Charge une liste Composite fournie par l'utilisateur ou par une URL CSV.

    Format tolérant : Symbol/Ticker, Name/Company, Sector.
    V5.9.14 : l'ancien univers étendu est retiré. Un fichier CSV fourni
    sert maintenant à renforcer la couverture du Composite uniquement.
    """
    safe_universe = "tsx_composite" if str(universe_key) == "tsx_full" else str(universe_key)
    if safe_universe != "tsx_composite":
        return pd.DataFrame()

    from core.universe import user_directory_paths

    frames: list[pd.DataFrame] = []
    for path in user_directory_paths():
        try:
            if path.startswith(("http://", "https://")):
                raw = pd.read_csv(path)
            else:
                candidate = Path(path)
                if not candidate.exists():
                    continue
                raw = pd.read_csv(candidate)
        except Exception:
            continue

        if raw.empty:
            continue

        columns = {str(column).lower().strip(): column for column in raw.columns}
        symbol_column = next(
            (columns[key] for key in columns if key in {"symbol", "ticker", "root", "security symbol"}),
            None,
        )
        name_column = next(
            (columns[key] for key in columns if key in {"name", "company", "company name", "issuer name"}),
            None,
        )
        sector_column = next(
            (columns[key] for key in columns if "sector" in key),
            None,
        )

        if symbol_column is None:
            continue

        frame = pd.DataFrame()
        frame["Ticker"] = raw[symbol_column].map(normalise_tmx_symbol)
        frame = frame[frame["Ticker"].str.match(r"^[A-Z0-9]{1,8}(?:\.[A-Z0-9]{1,4})?$", na=False)]
        frame["Nom"] = raw[name_column].astype(str) if name_column else frame["Ticker"]
        frame["Secteur"] = raw[sector_column].astype(str) if sector_column else "Autre"
        frame["PoidsIndice"] = np.nan
        frame["YahooTicker"] = frame["Ticker"].map(raw_to_yahoo)
        frame["SourceComposition"] = "Répertoire Composite fourni"
        frame["Univers"] = get_universe(safe_universe).short_label
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["Ticker"], keep="first")
        .reset_index(drop=True)
    )


def _normalise_constituents(frame: pd.DataFrame, universe_key: str) -> pd.DataFrame:
    if frame.empty:
        return frame

    result = frame.copy()
    result["Ticker"] = result["Ticker"].astype(str).str.strip().str.upper()
    result["YahooTicker"] = result["YahooTicker"].fillna(result["Ticker"].map(raw_to_yahoo))
    result = result.drop_duplicates(subset=["YahooTicker"], keep="first")

    result["PoidsIndice"] = pd.to_numeric(result["PoidsIndice"], errors="coerce")
    if result["PoidsIndice"].isna().all() or result["PoidsIndice"].fillna(0).sum() <= 0:
        result["PoidsIndice"] = 100 / max(len(result), 1)
    else:
        missing = result["PoidsIndice"].isna()
        if missing.any():
            remaining = max(0.0, 100 - result.loc[~missing, "PoidsIndice"].sum())
            result.loc[missing, "PoidsIndice"] = remaining / max(missing.sum(), 1)

    result["Nom"] = result["Nom"].fillna(result["Ticker"]).astype(str)
    result["Secteur"] = result["Secteur"].fillna("Autre").replace({"": "Autre"}).astype(str)
    result["Univers"] = get_universe(universe_key).short_label

    columns = [
        "Ticker",
        "Nom",
        "Secteur",
        "PoidsIndice",
        "YahooTicker",
        "SourceComposition",
        "Univers",
    ]
    return result[columns].sort_values("PoidsIndice", ascending=False).reset_index(drop=True)


def fallback_constituents(universe_key: str | None = None) -> pd.DataFrame:
    key = "tsx_composite" if str(universe_key or "") == "tsx_full" else (universe_key or current_universe_key())
    return seed_constituents(key)


@st.cache_data(ttl=43_200, max_entries=8, show_spinner=False)
def _load_constituents_cached(universe_key: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    universe = get_universe(universe_key)
    diagnostics: dict[str, Any] = {
        "expected": universe.expected_count,
        "universe_key": universe.key,
        "universe_label": universe.label,
        "source": universe.source_kind,
        "downloaded_at": datetime.now(TORONTO_TZ).isoformat(),
        "error": "",
        "snapshot_limit": universe.snapshot_limit,
        "history_limit": universe.history_limit,
    }

    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    # 1. Répertoire complet fourni par l'utilisateur, prioritaire pour TSX complet.
    try:
        user_directory = _load_user_tsx_directory(universe_key)
        if not user_directory.empty:
            frames.append(user_directory)
    except Exception as exc:
        errors.append(f"Répertoire utilisateur : {type(exc).__name__}: {exc}")

    # 2. Holdings ETF officiels BlackRock.
    for url in universe.holdings_urls:
        try:
            frames.append(_download_blackrock_holdings(url, universe_key))
        except Exception as exc:
            errors.append(f"BlackRock : {type(exc).__name__}: {exc}")

    if frames:
        result = pd.concat(frames, ignore_index=True)
        result = _normalise_constituents(result, universe_key)
        if not result.empty:
            diagnostics.update(
                {
                    "actual": len(result),
                    "status": "OK",
                    "source": result["SourceComposition"].mode().iloc[0],
                    "errors": errors,
                }
            )
            return result, diagnostics

    result = fallback_constituents(universe_key)
    diagnostics.update(
        {
            "actual": len(result),
            "status": "Liste de secours",
            "source": result["SourceComposition"].mode().iloc[0] if not result.empty else "Secours",
            "error": " | ".join(errors),
            "errors": errors,
        }
    )
    return result, diagnostics


def load_constituents(universe_key: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    key = universe_key or current_universe_key()
    if str(key) == "tsx_full":
        key = "tsx_composite"
    return _load_constituents_cached(key)


@st.cache_data(ttl=15, max_entries=8, show_spinner=False)
def fetch_market_snapshot(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Télécharge un snapshot groupé et conserve le dernier résultat valide.

    En cas de limitation temporaire de Yahoo, Anatole continue d'afficher la
    dernière donnée connue au lieu de vider entièrement le cockpit.
    """
    tickers = tuple(dict.fromkeys(tickers))
    if not tickers:
        return pd.DataFrame()

    try:
        daily = yf.download(
            tickers=list(tickers),
            period="8d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
            prepost=False,
            timeout=12,
        )
    except Exception:
        return _last_good_snapshot(tickers)

    is_open, _ = market_status()
    use_intraday = is_open and _use_intraday_snapshot(len(tickers))
    if use_intraday:
        try:
            intraday = yf.download(
                tickers=list(tickers),
                period="1d",
                interval="5m",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
                prepost=False,
                timeout=10,
            )
        except Exception:
            intraday = pd.DataFrame()
    else:
        intraday = pd.DataFrame()

    rows: list[dict[str, Any]] = []
    timestamp = datetime.now(TORONTO_TZ)

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

        current = (
            float(intraday_close.iloc[-1])
            if not intraday_close.empty
            else float(daily_close.iloc[-1])
        )
        previous = (
            float(daily_close.iloc[-2])
            if len(daily_close) >= 2
            else np.nan
        )
        variation = (
            ((current - previous) / previous) * 100
            if previous and not np.isnan(previous)
            else np.nan
        )
        high = (
            safe_float(
                pd.to_numeric(
                    intraday_frame.get("High"), errors="coerce"
                ).max()
            )
            if not intraday_frame.empty and "High" in intraday_frame
            else safe_float(daily_frame["High"].iloc[-1])
            if not daily_frame.empty and "High" in daily_frame
            else np.nan
        )
        low = (
            safe_float(
                pd.to_numeric(
                    intraday_frame.get("Low"), errors="coerce"
                ).min()
            )
            if not intraday_frame.empty and "Low" in intraday_frame
            else safe_float(daily_frame["Low"].iloc[-1])
            if not daily_frame.empty and "Low" in daily_frame
            else np.nan
        )
        volume = (
            safe_float(
                pd.to_numeric(
                    intraday_frame.get("Volume"), errors="coerce"
                ).sum()
            )
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
                "Horodatage": timestamp,
                "SourceCours": "Yahoo Finance",
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return _last_good_snapshot(tickers)

    store = _market_snapshot_store()
    frames = store.setdefault("frames", {})
    if isinstance(frames, dict):
        frames[_snapshot_key(tickers)] = result.copy()
    store["updated_at"] = timestamp
    return result


@st.cache_data(ttl=1_800, max_entries=32, show_spinner=False)
def fetch_batch_history(
    tickers: tuple[str, ...], period: str = "1y", interval: str = "1d"
) -> dict[str, pd.DataFrame]:
    tickers = tuple(dict.fromkeys(str(ticker) for ticker in tickers if str(ticker or "").strip()))
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
        timeout=15,
    )
    return {
        ticker: extract_ticker_frame(data, ticker)
        for ticker in tickers
    }


@st.cache_data(ttl=30, max_entries=128, show_spinner=False)
def fetch_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    data = yf.download(
        tickers=ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        prepost=False,
        threads=True,
        timeout=15,
    )
    return extract_ticker_frame(data, ticker)


@st.cache_data(ttl=21_600, max_entries=128, show_spinner=False)
def fetch_company_info(ticker: str) -> dict[str, Any]:
    """Return the broadest company profile available without requiring an API key.

    Yahoo's full ``info`` payload can occasionally be unavailable or rate-limited.
    Anatole therefore merges it with ``fast_info`` and history metadata so that
    basic market fields remain usable whenever possible.
    """
    stock = yf.Ticker(ticker)
    info: dict[str, Any] = {}

    try:
        raw_info = stock.get_info()
        if isinstance(raw_info, dict):
            info.update(raw_info)
    except Exception:
        try:
            raw_info = stock.info
            if isinstance(raw_info, dict):
                info.update(raw_info)
        except Exception:
            pass

    fast_mapping = {
        "currency": "currency",
        "exchange": "exchange",
        "timezone": "exchangeTimezoneName",
        "last_price": "currentPrice",
        "market_cap": "marketCap",
        "shares": "sharesOutstanding",
        "year_high": "fiftyTwoWeekHigh",
        "year_low": "fiftyTwoWeekLow",
        "previous_close": "previousClose",
        "open": "open",
        "day_high": "dayHigh",
        "day_low": "dayLow",
        "last_volume": "volume",
        "ten_day_average_volume": "averageDailyVolume10Day",
        "three_month_average_volume": "averageVolume",
        "fifty_day_average": "fiftyDayAverage",
        "two_hundred_day_average": "twoHundredDayAverage",
    }
    try:
        fast = dict(stock.fast_info)
        for fast_key, info_key in fast_mapping.items():
            value = fast.get(fast_key)
            if info.get(info_key) in (None, "") and value not in (None, ""):
                info[info_key] = value
    except Exception:
        pass

    try:
        metadata = stock.get_history_metadata()
        if isinstance(metadata, dict):
            metadata_mapping = {
                "currency": "currency",
                "exchangeName": "exchange",
                "instrumentType": "quoteType",
                "regularMarketPrice": "currentPrice",
                "previousClose": "previousClose",
                "longName": "longName",
                "shortName": "shortName",
            }
            for source_key, target_key in metadata_mapping.items():
                value = metadata.get(source_key)
                if info.get(target_key) in (None, "") and value not in (None, ""):
                    info[target_key] = value
    except Exception:
        pass

    # Le secours TradingView n'est appelé que si plusieurs champs essentiels
    # sont absents. Cela conserve une bonne couverture sans ajouter une requête
    # externe inutile à chaque ouverture de fiche.
    essential_fields = (
        "marketCap",
        "enterpriseValue",
        "trailingPE",
        "priceToBook",
        "sector",
        "industry",
    )
    missing_essential = sum(
        info.get(field) in (None, "")
        for field in essential_fields
    )
    tv: dict[str, Any] = {}
    if missing_essential >= 2:
        tv = fetch_tradingview_fundamentals(ticker)
        info = merge_tradingview_into_info(info, tv)

    if tv:
        info.setdefault(
            "anatoleFundamentalSource",
            "Yahoo Finance + TradingView",
        )
    else:
        info.setdefault("anatoleFundamentalSource", "Yahoo Finance")

    return info


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


@st.cache_data(ttl=86_400, max_entries=16, show_spinner=False)
def fetch_fundamentals(tickers: tuple[str, ...]) -> pd.DataFrame:
    tickers = tuple(dict.fromkeys(str(ticker) for ticker in tickers if str(ticker or "").strip()))
    rows: list[dict[str, Any]] = []
    workers = min(_env_positive_int("ANATOLE_FUNDAMENTAL_WORKERS", 5), max(len(tickers), 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_one_fundamental, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            try:
                rows.append(future.result())
            except Exception:
                rows.append({"YahooTicker": futures[future]})
    return pd.DataFrame(rows)


def _fetch_stock_news_uncached(ticker: str) -> list[dict[str, str]]:
    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception:
        return []

    # Yahoo peut retourner beaucoup d'éléments ou répondre lentement.
    # On limite volontairement le volume par titre pour éviter les 502.
    max_per_ticker = int(os.getenv("ANATOLE_NEWS_PER_TICKER", "5"))
    articles: list[dict[str, str]] = []
    for item in raw_news[:max_per_ticker]:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        source = content if isinstance(content, dict) else item
        provider_value = source.get("provider")
        if isinstance(provider_value, dict):
            publisher = provider_value.get("displayName", "")
        else:
            publisher = item.get("publisher", "") or str(
                provider_value or ""
            )
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
        published = (
            source.get("pubDate")
            or source.get("displayTime")
            or item.get("providerPublishTime")
        )
        timestamp = parse_timestamp(published)
        articles.append(
            {
                "Ticker": ticker,
                "Titre": str(title),
                "URL": str(url),
                "Source": str(publisher),
                "Resume": str(summary),
                "Date": (
                    timestamp.isoformat()
                    if timestamp is not None
                    else ""
                ),
            }
        )
    return articles


@st.cache_data(ttl=900, max_entries=256, show_spinner=False)
def fetch_stock_news(ticker: str) -> list[dict[str, str]]:
    return _fetch_stock_news_uncached(ticker)


@st.cache_data(ttl=900, max_entries=64, show_spinner=False)
def fetch_news_bundle(tickers: tuple[str, ...]) -> list[dict[str, str]]:
    """Récupère plusieurs fils d'actualité avec garde anti-502.

    La page Actualités ne doit jamais faire tomber l'application si Yahoo
    répond lentement. Les appels sont donc bornés en nombre, en durée et en
    volume d'articles.
    """
    if not tickers:
        return []

    max_tickers = int(os.getenv("ANATOLE_NEWS_MAX_TICKERS", "4"))
    max_workers = int(os.getenv("ANATOLE_NEWS_WORKERS", "1"))
    timeout_seconds = int(os.getenv("ANATOLE_NEWS_TIMEOUT", "12"))
    max_articles = int(os.getenv("ANATOLE_NEWS_MAX_ARTICLES", "35"))

    selected = tuple(dict.fromkeys(tickers))[:max_tickers]
    articles: list[dict[str, str]] = []

    executor = ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(selected))))
    futures = {
        executor.submit(_fetch_stock_news_uncached, ticker): ticker
        for ticker in selected
    }

    try:
        for future in as_completed(futures, timeout=timeout_seconds):
            try:
                articles.extend(future.result(timeout=1))
            except Exception:
                continue
            if len(articles) >= max_articles:
                break
    except TimeoutError:
        # Une source lente ne doit pas provoquer de crash ou de 502.
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for article in articles:
        key = (
            str(article.get("URL") or "").strip()
            or str(article.get("Titre") or "").strip().lower()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)
        if len(deduped) >= max_articles:
            break

    return deduped


@st.cache_data(ttl=3_600, max_entries=128, show_spinner=False)
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


@st.cache_data(ttl=3_600, max_entries=32, show_spinner=False)
def fetch_calendar_bundles(
    tickers: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    if not tickers:
        return {}

    bundles: dict[str, dict[str, Any]] = {}
    workers = min(5, max(1, len(tickers)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_calendar_bundle, ticker): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                bundles[ticker] = future.result()
            except Exception:
                bundles[ticker] = {
                    "ticker": ticker,
                    "calendar": {},
                    "earnings": [],
                    "dividends": [],
                    "splits": [],
                    "key_dates": [],
                }
    return bundles


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


def _normalise_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _as_dataframe(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, pd.Series):
        return value.to_frame().T
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict) and value:
        try:
            return pd.DataFrame(value)
        except ValueError:
            return pd.DataFrame([value])
    return pd.DataFrame()


def _safe_stock_frame(stock: Any, method_name: str, attribute_name: str) -> pd.DataFrame:
    try:
        method = getattr(stock, method_name, None)
        if callable(method):
            frame = _as_dataframe(method())
            if not frame.empty:
                return frame
    except Exception:
        pass
    try:
        return _as_dataframe(getattr(stock, attribute_name, None))
    except Exception:
        return pd.DataFrame()


def _clean_external_frame(
    frame: pd.DataFrame,
    rename_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

    result = frame.copy().reset_index()
    if "index" in result.columns and result["index"].equals(pd.Series(range(len(result)))):
        result = result.drop(columns=["index"])

    rename_map = rename_map or {}
    translated: dict[Any, str] = {}
    for column in result.columns:
        key = _normalise_label(column)
        translated[column] = rename_map.get(key, str(column))
    result = result.rename(columns=translated)

    for column in result.columns:
        lowered = str(column).lower()
        if "date" in lowered or "début" in lowered:
            parsed = pd.to_datetime(result[column], errors="coerce")
            if parsed.notna().any():
                result[column] = parsed.dt.strftime("%Y-%m-%d")
        result[column] = result[column].map(
            lambda value: str(value) if isinstance(value, (dict, list, tuple, set)) else value
        )
    return result


def _statement_value(
    frame: pd.DataFrame,
    aliases: tuple[str, ...],
) -> tuple[float, str]:
    if frame is None or frame.empty:
        return np.nan, ""

    alias_keys = {_normalise_label(alias) for alias in aliases}
    matched_index = next(
        (index for index in frame.index if _normalise_label(index) in alias_keys),
        None,
    )
    if matched_index is None:
        return np.nan, ""

    row = frame.loc[matched_index]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    row = pd.to_numeric(row, errors="coerce").dropna()
    if row.empty:
        return np.nan, ""

    if all(isinstance(column, (pd.Timestamp, datetime, np.datetime64)) for column in row.index):
        row = row.sort_index(ascending=False)

    value = safe_float(row.iloc[0])
    period_value = row.index[0]
    try:
        period = pd.Timestamp(period_value).strftime("%Y-%m-%d")
    except Exception:
        period = str(period_value)
    return value, period


def _compact_statement_value(value: Any, decimals: int = 2) -> str:
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
    return f"{number:,.{decimals}f}"


def _statement_display(
    frame: pd.DataFrame,
    definitions: tuple[tuple[str, tuple[str, ...], bool], ...],
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

    columns = list(frame.columns)
    try:
        columns = sorted(columns, key=pd.Timestamp, reverse=True)
    except Exception:
        pass
    columns = columns[:4]

    records: list[dict[str, Any]] = []
    for label, aliases, is_per_share in definitions:
        alias_keys = {_normalise_label(alias) for alias in aliases}
        matched = next(
            (index for index in frame.index if _normalise_label(index) in alias_keys),
            None,
        )
        if matched is None:
            continue
        row = frame.loc[matched]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        record: dict[str, Any] = {"Indicateur": label}
        for column in columns:
            try:
                heading = pd.Timestamp(column).strftime("%Y-%m-%d")
            except Exception:
                heading = str(column)
            record[heading] = _compact_statement_value(
                row.get(column),
                decimals=2 if is_per_share else 2,
            )
        records.append(record)
    return pd.DataFrame(records)


def _stock_statement(stock: Any, method_name: str, attribute_name: str) -> pd.DataFrame:
    method = getattr(stock, method_name, None)
    if callable(method):
        for frequency in ("yearly", "trailing", "quarterly"):
            try:
                frame = _as_dataframe(method(freq=frequency))
                if not frame.empty:
                    return frame
            except Exception:
                continue
    try:
        frame = _as_dataframe(getattr(stock, attribute_name, None))
        if not frame.empty:
            return frame
    except Exception:
        pass
    return pd.DataFrame()


def _latest_two_statement_values(
    frame: pd.DataFrame, aliases: tuple[str, ...]
) -> tuple[float, float]:
    if frame is None or frame.empty:
        return np.nan, np.nan
    keys = {_normalise_label(alias) for alias in aliases}
    matched = next((idx for idx in frame.index if _normalise_label(idx) in keys), None)
    if matched is None:
        return np.nan, np.nan
    row = frame.loc[matched]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    values = pd.to_numeric(row, errors="coerce").dropna()
    try:
        values = values.sort_index(ascending=False)
    except Exception:
        pass
    latest = safe_float(values.iloc[0]) if len(values) else np.nan
    previous = safe_float(values.iloc[1]) if len(values) > 1 else np.nan
    return latest, previous


def _growth_rate(latest: float, previous: float) -> float:
    if np.isnan(latest) or np.isnan(previous) or previous == 0:
        return np.nan
    return (latest / abs(previous)) - 1


def _first_valid(*values: Any) -> float:
    for value in values:
        number = safe_float(value)
        if not np.isnan(number):
            return number
    return np.nan


@st.cache_data(ttl=21_600, max_entries=128, show_spinner=False)
def fetch_company_financials(ticker: str) -> dict[str, Any]:
    stock = yf.Ticker(ticker)
    info = fetch_company_info(ticker)
    tv = fetch_tradingview_fundamentals(ticker)
    info = merge_tradingview_into_info(info, tv)
    income = _stock_statement(stock, "get_income_stmt", "income_stmt")
    balance = _stock_statement(stock, "get_balance_sheet", "balance_sheet")
    cashflow = _stock_statement(stock, "get_cashflow", "cashflow")

    definitions: dict[str, tuple[pd.DataFrame, tuple[str, ...], tuple[str, ...]]] = {
        "revenue": (income, ("Total Revenue", "Operating Revenue"), ("totalRevenue",)),
        "gross_profit": (income, ("Gross Profit",), ("grossProfits",)),
        "operating_income": (income, ("Operating Income", "EBIT"), ("operatingIncome",)),
        "ebitda": (income, ("EBITDA", "Normalized EBITDA"), ("ebitda",)),
        "net_income": (
            income,
            ("Net Income", "Net Income Common Stockholders"),
            ("netIncomeToCommon", "netIncome"),
        ),
        "eps": (income, ("Diluted EPS", "Basic EPS"), ("trailingEps",)),
        "assets": (balance, ("Total Assets",), ("totalAssets",)),
        "cash": (
            balance,
            ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
            ("totalCash",),
        ),
        "debt": (
            balance,
            ("Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"),
            ("totalDebt",),
        ),
        "equity": (
            balance,
            ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"),
            ("totalStockholderEquity",),
        ),
        "current_assets": (balance, ("Current Assets", "Total Current Assets"), ("totalCurrentAssets",)),
        "current_liabilities": (balance, ("Current Liabilities", "Total Current Liabilities"), ("totalCurrentLiabilities",)),
        "operating_cashflow": (
            cashflow,
            ("Operating Cash Flow", "Total Cash From Operating Activities"),
            ("operatingCashflow",),
        ),
        "capital_expenditure": (
            cashflow,
            ("Capital Expenditure", "Capital Expenditures"),
            tuple(),
        ),
        "free_cashflow": (cashflow, ("Free Cash Flow",), ("freeCashflow",)),
    }

    metrics: dict[str, dict[str, Any]] = {}
    for key, (frame, aliases, info_keys) in definitions.items():
        value, period = _statement_value(frame, aliases)
        source = "États financiers"
        if np.isnan(value):
            for info_key in info_keys:
                candidate = safe_float(info.get(info_key))
                if not np.isnan(candidate):
                    value = candidate
                    period = "TTM / dernier disponible"
                    source = "Profil de marché"
                    break
        metrics[key] = {"value": value, "period": period, "source": source}

    cfo = safe_float(metrics["operating_cashflow"]["value"])
    capex = safe_float(metrics["capital_expenditure"]["value"])
    if np.isnan(safe_float(metrics["free_cashflow"]["value"])) and not np.isnan(cfo) and not np.isnan(capex):
        metrics["free_cashflow"] = {
            "value": cfo + capex if capex < 0 else cfo - abs(capex),
            "period": metrics["operating_cashflow"]["period"],
            "source": "Calcul Anatole",
        }

    revenue = safe_float(metrics["revenue"]["value"])
    net_income = safe_float(metrics["net_income"]["value"])
    profit_margin = safe_float(info.get("profitMargins"))
    if np.isnan(profit_margin) and not np.isnan(revenue) and revenue != 0 and not np.isnan(net_income):
        profit_margin = net_income / revenue

    current_ratio = safe_float(info.get("currentRatio"))
    current_assets = safe_float(metrics["current_assets"]["value"])
    current_liabilities = safe_float(metrics["current_liabilities"]["value"])
    if np.isnan(current_ratio) and not np.isnan(current_assets) and current_liabilities not in (0, np.nan):
        current_ratio = current_assets / current_liabilities if current_liabilities else np.nan

    # Croissance calculée à partir des deux derniers exercices quand le profil
    # de marché ne fournit pas la donnée.
    revenue_latest, revenue_previous = _latest_two_statement_values(
        income, ("Total Revenue", "Operating Revenue")
    )
    income_latest, income_previous = _latest_two_statement_values(
        income, ("Net Income", "Net Income Common Stockholders")
    )
    calculated_revenue_growth = _growth_rate(revenue_latest, revenue_previous)
    calculated_earnings_growth = _growth_rate(income_latest, income_previous)

    equity = safe_float(metrics["equity"]["value"])
    assets = safe_float(metrics["assets"]["value"])
    debt = safe_float(metrics["debt"]["value"])
    cash_value = safe_float(metrics["cash"]["value"])
    shares = _first_valid(info.get("sharesOutstanding"), tv.get("total_shares_outstanding_current"))
    current_price = _first_valid(info.get("currentPrice"), tv.get("close"))
    market_cap = _first_valid(info.get("marketCap"), tv.get("market_cap_basic"))
    if np.isnan(market_cap) and not np.isnan(shares) and not np.isnan(current_price):
        market_cap = shares * current_price
        info["marketCap"] = market_cap

    enterprise_value = _first_valid(info.get("enterpriseValue"), tv.get("enterprise_value_fq"))
    if np.isnan(enterprise_value) and not np.isnan(market_cap):
        enterprise_value = market_cap
        if not np.isnan(debt):
            enterprise_value += debt
        if not np.isnan(cash_value):
            enterprise_value -= cash_value
        info["enterpriseValue"] = enterprise_value

    trailing_pe = _first_valid(info.get("trailingPE"), tv.get("price_earnings_ttm"))
    if np.isnan(trailing_pe) and not np.isnan(market_cap) and not np.isnan(net_income) and net_income > 0:
        trailing_pe = market_cap / net_income
        info["trailingPE"] = trailing_pe

    price_to_book = _first_valid(info.get("priceToBook"), tv.get("price_book_fq"))
    if np.isnan(price_to_book) and not np.isnan(market_cap) and not np.isnan(equity) and equity > 0:
        price_to_book = market_cap / equity
        info["priceToBook"] = price_to_book

    revenue_growth = _first_valid(
        info.get("revenueGrowth"), tv.get("total_revenue_yoy_growth_ttm"), calculated_revenue_growth
    )
    earnings_growth = _first_valid(
        info.get("earningsGrowth"), tv.get("net_income_yoy_growth_ttm"),
        tv.get("earnings_per_share_diluted_yoy_growth_ttm"), calculated_earnings_growth
    )
    return_on_equity = _first_valid(info.get("returnOnEquity"), tv.get("return_on_equity"))
    if np.isnan(return_on_equity) and not np.isnan(net_income) and not np.isnan(equity) and equity != 0:
        return_on_equity = net_income / equity
    return_on_assets = _first_valid(info.get("returnOnAssets"), tv.get("return_on_assets"))
    if np.isnan(return_on_assets) and not np.isnan(net_income) and not np.isnan(assets) and assets != 0:
        return_on_assets = net_income / assets
    debt_to_equity = _first_valid(info.get("debtToEquity"), tv.get("debt_to_equity"))
    if np.isnan(debt_to_equity) and not np.isnan(debt) and not np.isnan(equity) and equity != 0:
        debt_to_equity = debt / equity
    info["debtToEquity"] = debt_to_equity

    metrics.update(
        {
            "profit_margin": {"value": profit_margin, "period": "TTM", "source": "Calcul / profil"},
            "gross_margin": {"value": _first_valid(info.get("grossMargins"), tv.get("gross_margin")), "period": "TTM", "source": "Profil / TradingView"},
            "operating_margin": {"value": _first_valid(info.get("operatingMargins"), tv.get("operating_margin")), "period": "TTM", "source": "Profil / TradingView"},
            "revenue_growth": {"value": revenue_growth, "period": "YoY", "source": "Profil / TradingView / calcul"},
            "earnings_growth": {"value": earnings_growth, "period": "YoY", "source": "Profil / TradingView / calcul"},
            "return_on_equity": {"value": return_on_equity, "period": "TTM", "source": "Profil / TradingView / calcul"},
            "return_on_assets": {"value": return_on_assets, "period": "TTM", "source": "Profil / TradingView / calcul"},
            "current_ratio": {"value": current_ratio, "period": "Dernier disponible", "source": "Calcul / profil"},
            "quick_ratio": {"value": safe_float(info.get("quickRatio")), "period": "Dernier disponible", "source": "Profil de marché"},
        }
    )

    income_table = _statement_display(
        income,
        (
            ("Chiffre d'affaires", ("Total Revenue", "Operating Revenue"), False),
            ("Bénéfice brut", ("Gross Profit",), False),
            ("Résultat d'exploitation", ("Operating Income", "EBIT"), False),
            ("EBITDA", ("EBITDA", "Normalized EBITDA"), False),
            ("Résultat net", ("Net Income", "Net Income Common Stockholders"), False),
            ("BPA dilué", ("Diluted EPS", "Basic EPS"), True),
        ),
    )
    balance_table = _statement_display(
        balance,
        (
            ("Total de l'actif", ("Total Assets",), False),
            ("Trésorerie", ("Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"), False),
            ("Dette totale", ("Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"), False),
            ("Capitaux propres", ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"), False),
            ("Actif courant", ("Current Assets", "Total Current Assets"), False),
            ("Passif courant", ("Current Liabilities", "Total Current Liabilities"), False),
        ),
    )
    cashflow_table = _statement_display(
        cashflow,
        (
            ("Flux de trésorerie d'exploitation", ("Operating Cash Flow", "Total Cash From Operating Activities"), False),
            ("Dépenses en immobilisations", ("Capital Expenditure", "Capital Expenditures"), False),
            ("Flux de trésorerie disponible", ("Free Cash Flow",), False),
        ),
    )

    return {
        "info": info,
        "metrics": metrics,
        "income": income_table,
        "balance": balance_table,
        "cashflow": cashflow_table,
        "source": "Yahoo Finance, états financiers et TradingView Screener",
        "tradingview": tv,
    }


_RECOMMENDATION_LABELS = {
    "strong_buy": "Achat fort",
    "strongbuy": "Achat fort",
    "buy": "Achat",
    "hold": "Conserver",
    "underperform": "Sous-performance",
    "sell": "Vente",
    "strong_sell": "Vente forte",
    "strongsell": "Vente forte",
    "none": "Non couvert",
}


@st.cache_data(ttl=21_600, max_entries=128, show_spinner=False)
def fetch_analyst_consensus(ticker: str) -> dict[str, Any]:
    stock = yf.Ticker(ticker)
    info = fetch_company_info(ticker)

    targets: dict[str, Any] = {}
    try:
        raw_targets = stock.get_analyst_price_targets()
        if isinstance(raw_targets, dict):
            targets.update(raw_targets)
    except Exception:
        try:
            raw_targets = stock.analyst_price_targets
            if isinstance(raw_targets, dict):
                targets.update(raw_targets)
        except Exception:
            pass

    summary = _safe_stock_frame(
        stock,
        "get_recommendations_summary",
        "recommendations_summary",
    )
    if summary.empty:
        summary = _safe_stock_frame(stock, "get_recommendations", "recommendations")

    recommendation_rename = {
        "period": "Période",
        "strongbuy": "Achat fort",
        "buy": "Achat",
        "hold": "Conserver",
        "sell": "Vente",
        "strongsell": "Vente forte",
    }
    summary = _clean_external_frame(summary, recommendation_rename)

    upgrades = _safe_stock_frame(
        stock,
        "get_upgrades_downgrades",
        "upgrades_downgrades",
    )
    upgrades = _clean_external_frame(
        upgrades,
        {
            "gradedate": "Date",
            "firm": "Firme",
            "tograde": "Nouvelle recommandation",
            "fromgrade": "Ancienne recommandation",
            "action": "Action",
        },
    )

    def first_number(*values: Any) -> float:
        for value in values:
            number = safe_float(value)
            if not np.isnan(number):
                return number
        return np.nan

    current = first_number(targets.get("current"), info.get("currentPrice"), info.get("regularMarketPrice"))
    target_low = first_number(targets.get("low"), info.get("targetLowPrice"))
    target_high = first_number(targets.get("high"), info.get("targetHighPrice"))
    target_mean = first_number(targets.get("mean"), info.get("targetMeanPrice"))
    target_median = first_number(targets.get("median"), info.get("targetMedianPrice"))
    analyst_count = first_number(info.get("numberOfAnalystOpinions"))
    recommendation_mean = first_number(info.get("recommendationMean"))
    recommendation_key = str(info.get("recommendationKey") or "none").lower()
    recommendation = _RECOMMENDATION_LABELS.get(
        recommendation_key,
        recommendation_key.replace("_", " ").title() if recommendation_key else "Non couvert",
    )
    upside = ((target_mean / current) - 1) if current and not np.isnan(target_mean) else np.nan

    return {
        "metrics": {
            "recommendation": recommendation,
            "recommendation_mean": recommendation_mean,
            "analyst_count": analyst_count,
            "current_price": current,
            "target_low": target_low,
            "target_high": target_high,
            "target_mean": target_mean,
            "target_median": target_median,
            "upside_mean": upside,
        },
        "summary": summary,
        "upgrades": upgrades,
        "source": "Yahoo Finance via yfinance",
    }


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_recommendation_summary(ticker: str) -> pd.DataFrame:
    return fetch_analyst_consensus(ticker).get("summary", pd.DataFrame())


@st.cache_data(ttl=21_600, max_entries=128, show_spinner=False)
def fetch_insider_activity(ticker: str) -> dict[str, Any]:
    stock = yf.Ticker(ticker)
    info = fetch_company_info(ticker)

    transactions = _safe_stock_frame(
        stock,
        "get_insider_transactions",
        "insider_transactions",
    )
    transactions = _clean_external_frame(
        transactions,
        {
            "startdate": "Date",
            "date": "Date",
            "insider": "Initié",
            "name": "Initié",
            "position": "Fonction",
            "transaction": "Transaction",
            "text": "Description",
            "shares": "Actions",
            "value": "Valeur",
            "ownership": "Détention",
        },
    )

    purchases = _safe_stock_frame(
        stock,
        "get_insider_purchases",
        "insider_purchases",
    )
    purchases = _clean_external_frame(
        purchases,
        {
            "insiderpurchaseslast6m": "Activité sur 6 mois",
            "shares": "Actions",
            "trans": "Transactions",
        },
    )

    roster = _safe_stock_frame(
        stock,
        "get_insider_roster_holders",
        "insider_roster_holders",
    )
    roster = _clean_external_frame(
        roster,
        {
            "name": "Initié",
            "position": "Fonction",
            "mostrecenttransaction": "Transaction récente",
            "latesttransactiondate": "Date récente",
            "sharesowneddirectly": "Actions détenues directement",
            "sharesownedindirectly": "Actions détenues indirectement",
        },
    )

    ownership = {
        "held_percent_insiders": safe_float(info.get("heldPercentInsiders")),
        "held_percent_institutions": safe_float(info.get("heldPercentInstitutions")),
        "shares_outstanding": safe_float(info.get("sharesOutstanding")),
        "float_shares": safe_float(info.get("floatShares")),
    }

    return {
        "transactions": transactions,
        "purchases": purchases,
        "roster": roster,
        "ownership": ownership,
        "source": "Yahoo Finance via yfinance",
        "official_url": "https://www.sedi.ca/sedi/SVTReportsAccessController",
    }


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_insider_transactions(ticker: str) -> pd.DataFrame:
    return fetch_insider_activity(ticker).get("transactions", pd.DataFrame())


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
                timeout=12,
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
