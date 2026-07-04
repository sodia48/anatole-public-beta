from __future__ import annotations

from datetime import date, timedelta
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
REQUEST_TIMEOUT = 8


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_upcoming_ipos(
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Charge un calendrier IPO consolidé.

    Priorité des sources :
    1. fichier local data/ipo_calendar.csv, utile pour une bêta publique contrôlée ;
    2. Finnhub si FINNHUB_API_KEY est configurée ;
    3. Financial Modeling Prep si FMP_API_KEY est configurée ;
    4. Nasdaq public en meilleur effort, sans garantie de disponibilité.
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

    finnhub_key = get_secret("FINNHUB_API_KEY", "").strip()
    if finnhub_key:
        frame, status = _fetch_finnhub_ipo_calendar(start_date, end_date, finnhub_key)
        statuses["Finnhub"] = status
        if not frame.empty:
            frames.append(frame)
    else:
        statuses["Finnhub"] = "Clé absente"

    fmp_key = get_secret("FMP_API_KEY", "").strip()
    if fmp_key:
        frame, status = _fetch_fmp_ipo_calendar(start_date, end_date, fmp_key)
        statuses["Financial Modeling Prep"] = status
        if not frame.empty:
            frames.append(frame)
    else:
        statuses["Financial Modeling Prep"] = "Clé absente"

    nasdaq_enabled = str(get_secret("ANATOLE_ENABLE_NASDAQ_IPO_FALLBACK", "true")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if nasdaq_enabled:
        frame, status = _fetch_nasdaq_ipo_calendar()
        statuses["Nasdaq public"] = status
        if not frame.empty:
            frames.append(frame)
    else:
        statuses["Nasdaq public"] = "Désactivé"

    if not frames:
        return _empty_frame(), statuses

    combined = pd.concat(frames, ignore_index=True)
    combined = _clean_frame(combined)
    combined = _filter_dates(combined, start_date, end_date)
    combined = _deduplicate(combined)
    combined = _add_timing_columns(combined, today)
    combined = combined.sort_values(["DateTri", "Société"], ascending=[True, True])
    return combined.drop(columns=["DateTri"], errors="ignore"), statuses


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=IPO_COLUMNS + ["Jours avant IPO", "Moment"])


def _parse_date(value: str | date | None) -> date | None:
    if value in (None, ""):
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _request_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    response = requests.get(
        url,
        params=params or {},
        headers=headers or {},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


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


def _fetch_nasdaq_ipo_calendar() -> tuple[pd.DataFrame, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
        ),
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

    for key in ("ipoCalendar", "data", "rows", "items", "calendar"):
        value = payload.get(key)
        records = _extract_records(value)
        if records:
            return records

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("upcoming", "priced", "rows", "calendar"):
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
    lower_map = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
        lowered = name.lower()
        if lowered in lower_map and lower_map[lowered] not in (None, ""):
            return lower_map[lowered]
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
                "ipoDate",
                "pricedDate",
                "expectedDate",
                "effectiveDate",
            ),
        )
        company = _first_value(
            record,
            (
                "Société",
                "company",
                "companyName",
                "name",
                "Company Name",
                "issuerName",
            ),
        )
        symbol = _first_value(record, ("Symbole", "symbol", "ticker", "proposedTicker"))
        exchange = _first_value(record, ("Bourse", "exchange", "Exchange", "proposedExchange"))
        price = _first_value(
            record,
            (
                "Prix indicatif",
                "price",
                "priceRange",
                "Price Range",
                "proposedSharePrice",
                "offerPrice",
            ),
        )
        shares = _first_value(
            record,
            (
                "Actions offertes",
                "numberOfShares",
                "shares",
                "Shares Offered",
                "sharesOffered",
            ),
        )
        status = _first_value(record, ("Statut", "status", "dealStatus"))
        link = _first_value(record, ("Lien", "url", "link", "prospectusUrl", "filingUrl"))

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
    # Conserver les lignes sans date seulement si elles contiennent une société utile.
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
    return str(value).replace("&amp;", "&").strip()


def _normalise_status(value: Any) -> str:
    status = _clean_text(value)
    if not status:
        return "À venir"
    lowered = status.lower()
    if "expected" in lowered or "upcoming" in lowered:
        return "À venir"
    if "priced" in lowered:
        return "Prix fixé"
    if "filed" in lowered or "file" in lowered:
        return "Dossier déposé"
    if "withdraw" in lowered:
        return "Retirée"
    if "postpon" in lowered:
        return "Reportée"
    return status


def source_summary(statuses: dict[str, str]) -> str:
    if not statuses:
        return "Aucune source configurée."
    ok = [name for name, status in statuses.items() if status == "OK"]
    if ok:
        return "Sources actives : " + ", ".join(ok) + "."
    return "Aucune source IPO active pour l'instant."
