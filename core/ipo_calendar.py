from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

from core.config import DATA_DIR, TORONTO_TZ
from core.utils import get_secret

IPO_COLUMNS = [
    "Date",
    "Société",
    "Symbole",
    "Bourse",
    "Prix indicatif",
    "Actions offertes",
    "Statut",
    "Source",
    "Lien",
]

LOCAL_IPO_FILE = DATA_DIR / "ipo_calendar.csv"
REQUEST_TIMEOUT = 10

PUBLIC_HEADERS = {
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
    ),
}


@st.cache_data(ttl=60 * 60 * 4, show_spinner=False)
def load_upcoming_ipos(
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Charge un calendrier IPO consolidé.

    Priorité des sources :
    1. fichier local data/ipo_calendar.csv, utile pour une bêta publique contrôlée ;
    2. Finnhub si FINNHUB_API_KEY est configurée ;
    3. Financial Modeling Prep si FMP_API_KEY est configurée ;
    4. sources publiques sans clé API, en meilleur effort : Yahoo Finance,
       StockAnalysis et Nasdaq public.

    Note : les sources publiques ne garantissent pas une couverture exhaustive.
    Elles peuvent être différées, incomplètes, bloquées ou modifiées par les sites.
    """
    today = pd.Timestamp.now(tz=TORONTO_TZ).date()
    start_date = _parse_date(start) or today
    end_date = _parse_date(end) or (start_date + timedelta(days=180))

    frames: list[pd.DataFrame] = []
    statuses: dict[str, str] = {}

    local = _load_local_ipo_calendar(LOCAL_IPO_FILE)
    if not local.empty:
        frames.append(local)
        statuses["Fichier local"] = "OK"
    else:
        statuses["Fichier local"] = "Non configuré"

    finnhub_key = str(get_secret("FINNHUB_API_KEY", "") or "").strip()
    if finnhub_key:
        frame, status = _fetch_finnhub_ipo_calendar(start_date, end_date, finnhub_key)
        statuses["Finnhub"] = status
        if not frame.empty:
            frames.append(frame)
    else:
        statuses["Finnhub"] = "Clé absente"

    fmp_key = str(get_secret("FMP_API_KEY", "") or "").strip()
    if fmp_key:
        frame, status = _fetch_fmp_ipo_calendar(start_date, end_date, fmp_key)
        statuses["Financial Modeling Prep"] = status
        if not frame.empty:
            frames.append(frame)
    else:
        statuses["Financial Modeling Prep"] = "Clé absente"

    public_enabled = str(get_secret("ANATOLE_ENABLE_PUBLIC_IPO_SOURCES", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if public_enabled:
        for source_name, loader in (
            ("Yahoo Finance public", lambda: _fetch_yahoo_ipo_calendar(start_date, end_date)),
            ("StockAnalysis public", lambda: _fetch_stockanalysis_ipo_calendar()),
            ("Nasdaq public", lambda: _fetch_nasdaq_ipo_calendar()),
        ):
            frame, status = loader()
            statuses[source_name] = status
            if not frame.empty:
                frames.append(frame)
    else:
        statuses["Yahoo Finance public"] = "Désactivé"
        statuses["StockAnalysis public"] = "Désactivé"
        statuses["Nasdaq public"] = "Désactivé"

    if not frames:
        return _empty_frame(), statuses

    combined = pd.concat(frames, ignore_index=True)
    combined = _clean_frame(combined)
    combined = _filter_dates(combined, start_date, end_date)
    combined = _deduplicate(combined)
    combined = _add_timing_columns(combined, today)
    combined = combined.sort_values(["DateTri", "Société"], ascending=[True, True], na_position="last")
    return combined.drop(columns=["DateTri"], errors="ignore"), statuses


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=IPO_COLUMNS + ["Jours avant IPO", "Moment"])


def _parse_date(value: str | int | float | date | None) -> date | None:
    if value in (None, "", "-", "N/A", "n/a"):
        return None
    try:
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, (int, float)) and not pd.isna(value):
            # Certains endpoints Yahoo retournent des timestamps UNIX.
            if value > 10_000_000_000:
                return pd.to_datetime(value, unit="ms", errors="coerce").date()
            if value > 1_000_000_000:
                return pd.to_datetime(value, unit="s", errors="coerce").date()
        text = str(value).strip()
        if not text or text.lower() in {"tba", "tbd", "to be announced", "à confirmer"}:
            return None
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def _request_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    request_headers = dict(PUBLIC_HEADERS)
    if headers:
        request_headers.update(headers)
    response = requests.get(
        url,
        params=params or {},
        headers=request_headers,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _request_text(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    request_headers = dict(PUBLIC_HEADERS)
    if headers:
        request_headers.update(headers)
    response = requests.get(
        url,
        params=params or {},
        headers=request_headers,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def _load_local_ipo_calendar(path: Path) -> pd.DataFrame:
    if not path.exists():
        return _empty_frame()
    try:
        raw = pd.read_csv(path)
    except Exception:
        return _empty_frame()
    return _normalise_records(raw.to_dict("records"), source="Fichier local")


def _fetch_finnhub_ipo_calendar(
    start_date: date,
    end_date: date,
    api_key: str,
) -> tuple[pd.DataFrame, str]:
    try:
        payload = _request_json(
            "https://finnhub.io/api/v1/calendar/ipo",
            params={
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "token": api_key,
            },
        )
        records = payload.get("ipoCalendar", []) if isinstance(payload, dict) else []
        frame = _normalise_records(records, source="Finnhub")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    except Exception as exc:
        return _empty_frame(), f"Indisponible : {type(exc).__name__}"


def _fetch_fmp_ipo_calendar(
    start_date: date,
    end_date: date,
    api_key: str,
) -> tuple[pd.DataFrame, str]:
    endpoints = [
        "https://financialmodelingprep.com/stable/ipos-calendar",
        "https://financialmodelingprep.com/api/v3/ipo_calendar",
    ]
    errors: list[str] = []
    for endpoint in endpoints:
        try:
            payload = _request_json(
                endpoint,
                params={
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                    "apikey": api_key,
                },
            )
            records = _extract_records(payload)
            frame = _normalise_records(records, source="Financial Modeling Prep")
            if not frame.empty:
                return frame, "OK"
        except Exception as exc:
            errors.append(type(exc).__name__)
    if errors:
        return _empty_frame(), f"Indisponible : {', '.join(sorted(set(errors)))}"
    return _empty_frame(), "Aucune donnée"


def _fetch_yahoo_ipo_calendar(start_date: date, end_date: date) -> tuple[pd.DataFrame, str]:
    """Charge le calendrier IPO Yahoo Finance sans clé API.

    L'endpoint public peut changer ou retourner une couverture partielle.
    """
    endpoints = [
        "https://query1.finance.yahoo.com/v1/finance/calendar/ipo",
        "https://query2.finance.yahoo.com/v1/finance/calendar/ipo",
    ]
    errors: list[str] = []
    for endpoint in endpoints:
        try:
            payload = _request_json(
                endpoint,
                params={
                    "region": "US",
                    "lang": "en-US",
                    "formatted": "false",
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                    "corsDomain": "finance.yahoo.com",
                },
                headers={"Referer": "https://finance.yahoo.com/calendar/ipo/"},
            )
            records = _extract_records(payload)
            frame = _normalise_records(records, source="Yahoo Finance")
            if not frame.empty:
                return frame, "OK"
        except Exception as exc:
            errors.append(type(exc).__name__)
    if errors:
        return _empty_frame(), f"Indisponible : {', '.join(sorted(set(errors)))}"
    return _empty_frame(), "Aucune donnée"


def _fetch_stockanalysis_ipo_calendar() -> tuple[pd.DataFrame, str]:
    """Charge la table publique StockAnalysis sans clé API.

    Cette source est utile pour compléter Nasdaq/Yahoo, mais reste du scraping HTML
    en meilleur effort.
    """
    url = "https://stockanalysis.com/ipos/calendar/"
    try:
        html = _request_text(url, headers={"Referer": "https://stockanalysis.com/ipos/"})
        tables = pd.read_html(StringIO(html))
    except Exception as exc:
        return _empty_frame(), f"Indisponible : {type(exc).__name__}"

    frames: list[pd.DataFrame] = []
    for table in tables:
        if table.empty:
            continue
        columns = {str(column).lower(): column for column in table.columns}
        has_company = any(token in column for column in columns for token in ("company", "name"))
        has_date_or_symbol = any(token in column for column in columns for token in ("date", "symbol", "ticker"))
        if has_company and has_date_or_symbol:
            frames.append(_normalise_records(table.to_dict("records"), source="StockAnalysis"))

    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return _empty_frame(), "Aucune donnée"
    return pd.concat(frames, ignore_index=True), "OK"


def _fetch_nasdaq_ipo_calendar() -> tuple[pd.DataFrame, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/market-activity/ipos",
    }
    urls = [
        "https://api.nasdaq.com/api/ipo/calendar?date=upcoming",
        "https://api.nasdaq.com/api/ipo/calendar",
    ]
    errors: list[str] = []
    for url in urls:
        try:
            payload = _request_json(url, headers=headers)
            records = _extract_records(payload)
            frame = _normalise_records(records, source="Nasdaq")
            if not frame.empty:
                return frame, "OK"
        except Exception as exc:
            errors.append(type(exc).__name__)
    if errors:
        return _empty_frame(), f"Indisponible : {', '.join(sorted(set(errors)))}"
    return _empty_frame(), "Aucune donnée"


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in (
        "ipoCalendar",
        "events",
        "data",
        "rows",
        "items",
        "calendar",
        "result",
        "finance",
    ):
        value = payload.get(key)
        records = _extract_records(value)
        if records:
            return records

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("upcoming", "priced", "rows", "calendar", "events"):
            records = _extract_records(data.get(key))
            if records:
                return records
        nested: list[dict[str, Any]] = []
        for value in data.values():
            nested.extend(_extract_records(value))
        if nested:
            return nested

    nested: list[dict[str, Any]] = []
    for value in payload.values():
        nested.extend(_extract_records(value))
    return nested


def _first_value(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    lower_map = {str(key).lower().strip(): value for key, value in record.items()}
    compact_map = {str(key).lower().replace(" ", "").replace("_", "").strip(): value for key, value in record.items()}
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
        lowered = name.lower().strip()
        if lowered in lower_map and lower_map[lowered] not in (None, ""):
            return lower_map[lowered]
        compact = lowered.replace(" ", "").replace("_", "")
        if compact in compact_map and compact_map[compact] not in (None, ""):
            return compact_map[compact]
    return ""


def _normalise_records(records: list[dict[str, Any]], source: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        ipo_date = _first_value(
            record,
            (
                "Date",
                "date",
                "IPO Date",
                "ipoDate",
                "pricedDate",
                "pricingDate",
                "expectedDate",
                "expectedPricingDate",
                "effectiveDate",
                "startDate",
                "firstTradeDate",
                "listingDate",
                "timestamp",
                "unixDate",
            ),
        )
        company = _first_value(
            record,
            (
                "Société",
                "company",
                "companyName",
                "Company Name",
                "issuerName",
                "issuer",
                "name",
                "Name",
            ),
        )
        symbol = _first_value(
            record,
            (
                "Symbole",
                "symbol",
                "Symbol",
                "ticker",
                "Ticker",
                "proposedTicker",
                "proposedTickerSymbol",
                "stock",
                "Stock",
            ),
        )
        exchange = _first_value(
            record,
            (
                "Bourse",
                "exchange",
                "Exchange",
                "proposedExchange",
                "stockExchange",
                "listingExchange",
            ),
        )
        price = _first_value(
            record,
            (
                "Prix indicatif",
                "price",
                "Price",
                "priceRange",
                "Price Range",
                "proposedSharePrice",
                "offerPrice",
                "ipoPrice",
                "expectedPrice",
                "sharePrice",
            ),
        )
        shares = _first_value(
            record,
            (
                "Actions offertes",
                "numberOfShares",
                "shares",
                "Shares",
                "Shares Offered",
                "sharesOffered",
                "offeredShares",
                "offerShares",
            ),
        )
        status = _first_value(record, ("Statut", "status", "Status", "dealStatus", "eventType", "type"))
        link = _first_value(record, ("Lien", "url", "link", "prospectusUrl", "filingUrl", "webUrl"))

        if not company and not symbol:
            continue

        rows.append(
            {
                "Date": _format_date(ipo_date),
                "Société": _clean_text(company),
                "Symbole": _clean_text(symbol).upper(),
                "Bourse": _clean_text(exchange).upper(),
                "Prix indicatif": _clean_text(price),
                "Actions offertes": _clean_text(shares),
                "Statut": _normalise_status(status),
                "Source": source,
                "Lien": _clean_text(link),
            }
        )
    if not rows:
        return _empty_frame()
    return pd.DataFrame(rows)


def _clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_frame()
    work = frame.copy()
    for column in IPO_COLUMNS:
        if column not in work.columns:
            work[column] = ""
    work = work[IPO_COLUMNS]
    for column in IPO_COLUMNS:
        work[column] = work[column].fillna("").astype(str).str.strip()
    work["DateTri"] = pd.to_datetime(work["Date"], errors="coerce")
    return work


def _filter_dates(frame: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    if frame.empty or "DateTri" not in frame.columns:
        return frame
    work = frame.copy()
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    dated = work["DateTri"].notna()
    in_range = (work["DateTri"] >= start_ts) & (work["DateTri"] <= end_ts)
    # Conserver les lignes sans date si elles contiennent une société utile :
    # certaines IPO sont annoncées avant que la date de cotation soit fixée.
    return work.loc[(dated & in_range) | (~dated & work["Société"].ne(""))].copy()


def _deduplicate(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    work = frame.copy()
    work["_dedupe_symbol"] = work["Symbole"].str.upper().str.strip()
    work["_dedupe_name"] = work["Société"].str.lower().str.strip()
    work["_dedupe_date"] = work["Date"].str.strip()
    work = work.drop_duplicates(
        subset=["_dedupe_symbol", "_dedupe_name", "_dedupe_date"],
        keep="first",
    )
    return work.drop(columns=["_dedupe_symbol", "_dedupe_name", "_dedupe_date"], errors="ignore")


def _add_timing_columns(frame: pd.DataFrame, today: date) -> pd.DataFrame:
    if frame.empty:
        return _empty_frame()
    work = frame.copy()
    days: list[Any] = []
    moments: list[str] = []
    for value in work.get("DateTri", []):
        if pd.isna(value):
            days.append(pd.NA)
            moments.append("Date à confirmer")
            continue
        delta = (pd.Timestamp(value).date() - today).days
        days.append(delta)
        if delta < 0:
            moments.append("Déjà passé")
        elif delta == 0:
            moments.append("Aujourd'hui")
        elif delta <= 7:
            moments.append("Cette semaine")
        elif delta <= 30:
            moments.append("Dans 30 jours")
        else:
            moments.append("Plus tard")
    work["Jours avant IPO"] = days
    work["Moment"] = moments
    return work


def _format_date(value: Any) -> str:
    parsed = _parse_date(value)
    if parsed is None:
        return "À confirmer"
    return parsed.isoformat()


def _clean_text(value: Any) -> str:
    if value in (None, "nan", "NaN"):
        return ""
    text = str(value).replace("&amp;", "&").strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _normalise_status(value: Any) -> str:
    status = _clean_text(value)
    if not status:
        return "À venir"
    lowered = status.lower()
    if "expected" in lowered or "upcoming" in lowered or "pricing" in lowered:
        return "À venir"
    if "priced" in lowered:
        return "Prix fixé"
    if "filed" in lowered or "filing" in lowered or "file" in lowered:
        return "Dossier déposé"
    if "withdraw" in lowered:
        return "Retirée"
    if "postpon" in lowered or "delayed" in lowered:
        return "Reportée"
    return status


def source_summary(statuses: dict[str, str]) -> str:
    if not statuses:
        return "Aucune source configurée."
    ok = [name for name, status in statuses.items() if str(status).startswith("OK")]
    if ok:
        return (
            "Sources actives : "
            + ", ".join(ok)
            + ". Couverture publique en meilleur effort : les IPO peuvent être modifiées, reportées ou absentes selon les sources."
        )
    return "Aucune source IPO active pour l'instant."
