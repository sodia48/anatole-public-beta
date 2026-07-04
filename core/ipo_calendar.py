from __future__ import annotations

from datetime import date, timedelta
from html import unescape
from pathlib import Path
from typing import Any
import re

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
REQUEST_TIMEOUT = 12

PUBLIC_HEADERS = {
    "Accept": "application/json, text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
}


@st.cache_data(ttl=60 * 60 * 4, show_spinner=False)
def load_upcoming_ipos(
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Charge un calendrier IPO consolidé.

    Anatole essaie d'abord les sources contrôlées, puis plusieurs sources
    publiques sans clé API. Les sources publiques restent en meilleur effort :
    elles peuvent être incomplètes, différées, bloquées ou changer de structure.
    """
    today = pd.Timestamp.now(tz=TORONTO_TZ).date()
    start_date = _parse_date(start) or today
    end_date = _parse_date(end) or (start_date + timedelta(days=180))

    frames: list[pd.DataFrame] = []
    statuses: dict[str, str] = {}

    local = _load_local_ipo_calendar(LOCAL_IPO_FILE)
    if not local.empty:
        frames.append(local)
        statuses["Fichier local"] = f"OK — {len(local)} ligne(s)"
    else:
        statuses["Fichier local"] = "Optionnel — non configuré"

    finnhub_key = str(get_secret("FINNHUB_API_KEY", "") or "").strip()
    if finnhub_key:
        frame, status = _fetch_finnhub_ipo_calendar(start_date, end_date, finnhub_key)
        statuses["Finnhub"] = _status_with_count(status, frame)
        if not frame.empty:
            frames.append(frame)
    else:
        statuses["Finnhub"] = "Optionnel — clé absente"

    fmp_key = str(get_secret("FMP_API_KEY", "") or "").strip()
    if fmp_key:
        frame, status = _fetch_fmp_ipo_calendar(start_date, end_date, fmp_key)
        statuses["Financial Modeling Prep"] = _status_with_count(status, frame)
        if not frame.empty:
            frames.append(frame)
    else:
        statuses["Financial Modeling Prep"] = "Optionnel — clé absente"

    public_enabled = str(get_secret("ANATOLE_ENABLE_PUBLIC_IPO_SOURCES", "true") or "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if public_enabled:
        public_loaders = (
            ("StockAnalysis public", lambda: _fetch_stockanalysis_ipo_calendar()),
            ("IPO Scoop public", lambda: _fetch_iposcoop_ipo_calendar()),
            ("Nasdaq public", lambda: _fetch_nasdaq_ipo_calendar()),
            ("Yahoo Finance public", lambda: _fetch_yahoo_ipo_calendar(start_date, end_date)),
        )
        for source_name, loader in public_loaders:
            frame, status = loader()
            statuses[source_name] = _status_with_count(status, frame)
            if not frame.empty:
                frames.append(frame)
    else:
        statuses["StockAnalysis public"] = "Désactivé"
        statuses["IPO Scoop public"] = "Désactivé"
        statuses["Nasdaq public"] = "Désactivé"
        statuses["Yahoo Finance public"] = "Désactivé"

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
            if value > 10_000_000_000:
                parsed = pd.to_datetime(value, unit="ms", errors="coerce")
                return None if pd.isna(parsed) else parsed.date()
            if value > 1_000_000_000:
                parsed = pd.to_datetime(value, unit="s", errors="coerce")
                return None if pd.isna(parsed) else parsed.date()
        text = str(value).strip()
        if not text or text.lower() in {
            "tba",
            "tbd",
            "to be announced",
            "à confirmer",
            "date à confirmer",
            "expected",
        }:
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
        return _empty_frame(), _friendly_error(exc)


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
            errors.append(_friendly_error(exc))
    return _empty_frame(), _combine_errors(errors)


def _fetch_yahoo_ipo_calendar(start_date: date, end_date: date) -> tuple[pd.DataFrame, str]:
    """Source publique Yahoo, conservée en complément.

    Dans certains environnements, Yahoo retourne une erreur HTTP ou demande des
    cookies. On ne l'utilise donc jamais comme source principale.
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
            errors.append(_friendly_error(exc))
    return _empty_frame(), _combine_errors(errors)


def _fetch_stockanalysis_ipo_calendar() -> tuple[pd.DataFrame, str]:
    """Charge StockAnalysis sans dépendre de pandas.read_html/lxml.

    La version précédente utilisait pd.read_html, ce qui provoquait parfois
    ImportError si lxml/html5lib n'était pas installé. Ici, on parse les tables
    HTML avec la bibliothèque standard pour éviter cette dépendance.
    """
    url = "https://stockanalysis.com/ipos/calendar/"
    try:
        html = _request_text(url, headers={"Referer": "https://stockanalysis.com/ipos/"})
        records = _extract_html_table_records(html, base_url="https://stockanalysis.com")
        frame = _normalise_records(records, source="StockAnalysis")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    except Exception as exc:
        return _empty_frame(), _friendly_error(exc)


def _fetch_iposcoop_ipo_calendar() -> tuple[pd.DataFrame, str]:
    """Complément public sans API pour élargir la couverture."""
    url = "https://www.iposcoop.com/ipo-calendar/"
    try:
        html = _request_text(url, headers={"Referer": "https://www.iposcoop.com/"})
        records = _extract_html_table_records(html, base_url="https://www.iposcoop.com")
        frame = _normalise_records(records, source="IPO Scoop")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    except Exception as exc:
        return _empty_frame(), _friendly_error(exc)


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
    collected: list[pd.DataFrame] = []
    for url in urls:
        try:
            payload = _request_json(url, headers=headers)
            records = _extract_records(payload)
            frame = _normalise_records(records, source="Nasdaq")
            if not frame.empty:
                collected.append(frame)
        except Exception as exc:
            errors.append(_friendly_error(exc))
    if collected:
        return pd.concat(collected, ignore_index=True), "OK"
    return _empty_frame(), _combine_errors(errors) if errors else "Aucune donnée"


def _extract_html_table_records(html: str, base_url: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    tables = re.findall(r"<table\b[^>]*>(.*?)</table>", html, flags=re.IGNORECASE | re.DOTALL)
    for table in tables:
        rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.IGNORECASE | re.DOTALL)
        if len(rows) < 2:
            continue

        header_cells = _extract_cells(rows[0], base_url=base_url)
        if not header_cells or len(header_cells) < 2:
            continue

        headers = [_normalise_header(cell) for cell in header_cells]
        useful_header = " ".join(headers).lower()
        if not any(token in useful_header for token in ("company", "société", "symbol", "ticker", "date", "ipo")):
            continue

        for row_html in rows[1:]:
            cells = _extract_cells(row_html, base_url=base_url)
            if len(cells) < 2:
                continue
            if len(cells) < len(headers):
                cells += [""] * (len(headers) - len(cells))
            record = {headers[index]: cells[index] for index in range(min(len(headers), len(cells)))}
            # Préserver un lien de prospectus/page société lorsqu'un href est présent dans la ligne.
            row_link = _extract_first_href(row_html, base_url=base_url)
            if row_link and not record.get("Lien"):
                record["Lien"] = row_link
            records.append(record)
    return records


def _extract_cells(row_html: str, base_url: str = "") -> list[str]:
    cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
    return [_strip_html(cell, base_url=base_url) for cell in cells]


def _extract_first_href(html: str, base_url: str = "") -> str:
    match = re.search(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
    if not match:
        return ""
    href = unescape(match.group(1)).strip()
    if href.startswith("/") and base_url:
        return base_url.rstrip("/") + href
    if href.startswith("http"):
        return href
    return ""


def _strip_html(value: str, base_url: str = "") -> str:
    text = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalise_header(value: Any) -> str:
    text = _clean_text(value)
    lower = text.lower().replace("\n", " ").strip()
    aliases = {
        "company": "Société",
        "company name": "Société",
        "name": "Société",
        "issuer": "Société",
        "issuer name": "Société",
        "symbol": "Symbole",
        "ticker": "Symbole",
        "proposed symbol": "Symbole",
        "proposed ticker": "Symbole",
        "stock": "Symbole",
        "date": "Date",
        "ipo date": "Date",
        "expected date": "Date",
        "offer date": "Date",
        "pricing date": "Date",
        "exchange": "Bourse",
        "market": "Bourse",
        "price": "Prix indicatif",
        "price range": "Prix indicatif",
        "range": "Prix indicatif",
        "shares": "Actions offertes",
        "shares offered": "Actions offertes",
        "offer amount": "Actions offertes",
        "status": "Statut",
        "type": "Statut",
        "url": "Lien",
        "link": "Lien",
    }
    return aliases.get(lower, text)


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
                "Offer Date",
                "offerDate",
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
                "Proposed Symbol",
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
                "market",
                "Market",
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
                "range",
                "Range",
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
                "Offer Amount",
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


def _friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    if isinstance(exc, requests.exceptions.HTTPError):
        return "Non disponible aujourd'hui — accès public refusé ou modifié"
    if isinstance(exc, requests.exceptions.Timeout):
        return "Non disponible aujourd'hui — délai d'attente dépassé"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Non disponible aujourd'hui — connexion impossible"
    if name == "ImportError":
        return "Non disponible aujourd'hui — dépendance de lecture HTML absente"
    return "Non disponible aujourd'hui — source publique instable"


def _combine_errors(errors: list[str]) -> str:
    if not errors:
        return "Aucune donnée"
    unique = []
    for error in errors:
        if error not in unique:
            unique.append(error)
    return unique[0] if len(unique) == 1 else "Non disponible aujourd'hui — plusieurs essais infructueux"


def _status_with_count(status: str, frame: pd.DataFrame) -> str:
    if str(status).startswith("OK"):
        return f"OK — {len(frame)} ligne(s)"
    return status


def source_summary(statuses: dict[str, str]) -> str:
    if not statuses:
        return "Aucune source configurée."
    ok = [name for name, status in statuses.items() if str(status).startswith("OK")]
    if ok:
        return (
            "Sources actives : "
            + ", ".join(ok)
            + ". Les sources publiques sans API sont utiles pour la veille, mais ne garantissent pas une couverture complète."
        )
    return "Aucune source IPO active pour l'instant. Ajoute un fichier local ou une clé API pour fiabiliser la couverture."
