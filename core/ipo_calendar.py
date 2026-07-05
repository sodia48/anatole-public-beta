from __future__ import annotations

from datetime import date, timedelta
from html import unescape
from pathlib import Path
from typing import Any
from difflib import SequenceMatcher
import re
import xml.etree.ElementTree as ET

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
    "Pays",
    "Type d’événement",
    "Prix indicatif",
    "Actions offertes",
    "Montant estimé",
    "Statut",
    "Source",
    "Lien",
]

LOCAL_IPO_FILE = DATA_DIR / "ipo_calendar.csv"
REQUEST_TIMEOUT = 8

# Ordre de confiance pour choisir la meilleure ligne lorsqu'une IPO est
# trouvée par plusieurs sources. Les sources contrôlées/locales passent
# avant les sites publics, puis Anatole fusionne les informations manquantes.
SOURCE_PRIORITY = {
    "Fichier local": 0,
    "Finnhub": 1,
    "Financial Modeling Prep": 2,
    "StockAnalysis": 3,
    "StockAnalysis Filings": 4,
    "Renaissance Capital": 5,
    "IPO Scoop": 6,
    "Nasdaq": 7,
    "NYSE": 8,
    "SEC EDGAR": 9,
    "TMX New Listings": 10,
    "MarketWatch": 11,
    "Investing.com": 12,
    "Yahoo Finance": 13,
}

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
            ("StockAnalysis filings public", lambda: _fetch_stockanalysis_filings()),
            ("Renaissance Capital public", lambda: _fetch_renaissance_ipo_calendar()),
            ("IPO Scoop public", lambda: _fetch_iposcoop_ipo_calendar()),
            ("Nasdaq public", lambda: _fetch_nasdaq_ipo_calendar()),
            ("NYSE public", lambda: _fetch_nyse_ipo_calendar()),
            ("SEC EDGAR S-1/F-1 public", lambda: _fetch_sec_ipo_filings()),
            ("TMX new listings public", lambda: _fetch_tmx_new_listings()),
            ("MarketWatch public", lambda: _fetch_marketwatch_ipo_calendar()),
            ("Investing.com public", lambda: _fetch_investing_ipo_calendar()),
            ("Yahoo Finance public", lambda: _fetch_yahoo_ipo_calendar(start_date, end_date)),
        )
        for source_name, loader in public_loaders:
            frame, status = loader()
            statuses[source_name] = _status_with_count(status, frame)
            if not frame.empty:
                frames.append(frame)
    else:
        statuses["StockAnalysis public"] = "Désactivé"
        statuses["StockAnalysis filings public"] = "Désactivé"
        statuses["Renaissance Capital public"] = "Désactivé"
        statuses["IPO Scoop public"] = "Désactivé"
        statuses["Nasdaq public"] = "Désactivé"
        statuses["NYSE public"] = "Désactivé"
        statuses["SEC EDGAR S-1/F-1 public"] = "Désactivé"
        statuses["TMX new listings public"] = "Désactivé"
        statuses["MarketWatch public"] = "Désactivé"
        statuses["Investing.com public"] = "Désactivé"
        statuses["Yahoo Finance public"] = "Désactivé"

    if not frames:
        return _empty_frame(), statuses

    combined = pd.concat(frames, ignore_index=True)
    combined = _clean_frame(combined)
    combined = _filter_dates(combined, start_date, end_date)
    combined = _deduplicate(combined)
    combined = _add_timing_columns(combined, today)
    combined = _add_quality_columns(combined)
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


def _fetch_stockanalysis_filings() -> tuple[pd.DataFrame, str]:
    """Ajoute le pipeline des sociétés ayant déposé un dossier IPO.

    Ces lignes ne garantissent pas une date d'IPO immédiate. Elles enrichissent
    le radar avec les sociétés qui ont déjà déposé un dossier d'entrée en
    bourse et qui peuvent ensuite apparaître dans le calendrier.
    """
    url = "https://stockanalysis.com/ipos/filings/"
    try:
        html = _request_text(url, headers={"Referer": "https://stockanalysis.com/ipos/"})
        records = _extract_html_table_records(html, base_url="https://stockanalysis.com")
        for record in records:
            record.setdefault("Statut", "Dossier déposé")
            record.setdefault("Type d’événement", "Dépôt IPO")
        frame = _normalise_records(records, source="StockAnalysis Filings")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    except Exception as exc:
        return _empty_frame(), _friendly_error(exc)


def _fetch_sec_ipo_filings() -> tuple[pd.DataFrame, str]:
    """Récupère les dépôts S-1/F-1 récents via le flux public EDGAR.

    Ce n'est pas un calendrier de pricing. C'est un radar de pipeline : S-1,
    S-1/A, F-1 et F-1/A signalent qu'une société a publié ou amendé un dossier
    d'introduction en bourse.
    """
    forms = ("S-1", "S-1/A", "F-1", "F-1/A")
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    user_agent = str(get_secret("SEC_USER_AGENT", "AnatoleMarketDashboard/1.0 contact@example.com") or "").strip()
    for form in forms:
        try:
            xml_text = _request_text(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "action": "getcurrent",
                    "type": form,
                    "owner": "exclude",
                    "count": "40",
                    "output": "atom",
                },
                headers={
                    "Accept": "application/atom+xml, application/xml, text/xml, */*",
                    "User-Agent": user_agent,
                    "Referer": "https://www.sec.gov/search-filings",
                },
            )
            records.extend(_extract_sec_atom_records(xml_text, form))
        except Exception as exc:
            errors.append(_friendly_error(exc))
    if records:
        frame = _normalise_records(records, source="SEC EDGAR")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    return _empty_frame(), _combine_errors(errors) if errors else "Aucune donnée"


def _fetch_tmx_new_listings() -> tuple[pd.DataFrame, str]:
    """Complément canadien : nouvelles inscriptions TSX/TSXV.

    TMX publie surtout des sociétés déjà listées/récemment listées, pas
    nécessairement un calendrier IPO futur. Anatole les sépare donc comme
    événement de marché canadien plutôt que comme date d'IPO confirmée.
    """
    url = "https://www.tsx.com/en/news/new-company-listings"
    try:
        html = _request_text(url, headers={"Referer": "https://www.tsx.com/"})
        records = _extract_html_table_records(html, base_url="https://www.tsx.com")
        for record in records:
            record.setdefault("Statut", "Nouvelle inscription")
            record.setdefault("Bourse", "TSX/TSXV")
            record.setdefault("Pays", "Canada")
            record.setdefault("Type d’événement", "Nouvelle inscription")
        frame = _normalise_records(records, source="TMX New Listings")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    except Exception as exc:
        return _empty_frame(), _friendly_error(exc)


def _extract_sec_atom_records(xml_text: str, form: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return records

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns) or root.findall("entry")
    for entry in entries:
        title_node = entry.find("atom:title", ns)
        if title_node is None:
            title_node = entry.find("title")
        updated_node = entry.find("atom:updated", ns)
        if updated_node is None:
            updated_node = entry.find("updated")
        link_node = entry.find("atom:link", ns)
        if link_node is None:
            link_node = entry.find("link")
        title = title_node.text if title_node is not None else ""
        updated = updated_node.text if updated_node is not None else ""
        link = link_node.attrib.get("href", "") if link_node is not None else ""
        company = _extract_company_from_sec_title(title, form)
        symbol = _extract_symbol_from_sec_title(title)
        if not company:
            continue
        records.append(
            {
                "Date": updated,
                "Société": company,
                "Symbole": symbol,
                "Bourse": "",
                "Pays": "États-Unis",
                "Type d’événement": "Dépôt réglementaire",
                "Statut": f"Dossier {form}",
                "Lien": link,
            }
        )
    return records


def _extract_company_from_sec_title(title: str, form: str) -> str:
    text = _strip_html(title)
    text = re.sub(rf"^\s*{re.escape(form)}\s*-\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(CIK.*$", "", text, flags=re.IGNORECASE).strip()
    return text


def _extract_symbol_from_sec_title(title: str) -> str:
    match = re.search(r"\(([A-Z][A-Z0-9.]{1,8})\)\s*(?:$|[-,])", title)
    return match.group(1).upper() if match else ""


def _fetch_renaissance_ipo_calendar() -> tuple[pd.DataFrame, str]:
    """Source publique spécialisée très utile pour le pipeline US.

    Renaissance Capital publie un calendrier IPO avec les IPO de la semaine,
    les IPO après la semaine courante et des sous-sections NYSE/Nasdaq.
    """
    url = "https://www.renaissancecapital.com/IPO-Center/Calendar"
    try:
        html = _request_text(url, headers={"Referer": "https://www.renaissancecapital.com/IPO-Center"})
        records = _extract_html_table_records(html, base_url="https://www.renaissancecapital.com")
        if not records:
            records = _extract_renaissance_text_records(html)
        frame = _normalise_records(records, source="Renaissance Capital")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    except Exception as exc:
        return _empty_frame(), _friendly_error(exc)


def _fetch_nyse_ipo_calendar() -> tuple[pd.DataFrame, str]:
    """Complément NYSE en meilleur effort.

    La page NYSE est parfois rendue dynamiquement. Lorsqu'elle expose des
    tables HTML ou du contenu indexable, Anatole l'intègre sans bloquer.
    """
    urls = [
        "https://www.nyse.com/ipo-center/filings",
        "https://www.nyse.com/ipo-center/recent-ipo",
    ]
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for url in urls:
        try:
            html = _request_text(url, headers={"Referer": "https://www.nyse.com/ipo-center"})
            records = _extract_html_table_records(html, base_url="https://www.nyse.com")
            frame = _normalise_records(records, source="NYSE")
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            errors.append(_friendly_error(exc))
    if frames:
        return pd.concat(frames, ignore_index=True), "OK"
    return _empty_frame(), _combine_errors(errors) if errors else "Aucune donnée"


def _fetch_marketwatch_ipo_calendar() -> tuple[pd.DataFrame, str]:
    """Complément public MarketWatch."""
    url = "https://www.marketwatch.com/investing/ipo"
    try:
        html = _request_text(url, headers={"Referer": "https://www.marketwatch.com/"})
        records = _extract_html_table_records(html, base_url="https://www.marketwatch.com")
        frame = _normalise_records(records, source="MarketWatch")
        return frame, "OK" if not frame.empty else "Aucune donnée"
    except Exception as exc:
        return _empty_frame(), _friendly_error(exc)


def _fetch_investing_ipo_calendar() -> tuple[pd.DataFrame, str]:
    """Complément public Investing.com."""
    urls = [
        "https://www.investing.com/ipo-calendar/",
        "https://ca.investing.com/ipo-calendar/",
    ]
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for url in urls:
        try:
            html = _request_text(url, headers={"Referer": "https://www.investing.com/"})
            records = _extract_html_table_records(html, base_url="https://www.investing.com")
            frame = _normalise_records(records, source="Investing.com")
            if not frame.empty:
                frames.append(frame)
        except Exception as exc:
            errors.append(_friendly_error(exc))
    if frames:
        return pd.concat(frames, ignore_index=True), "OK"
    return _empty_frame(), _combine_errors(errors) if errors else "Aucune donnée"


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


def _extract_renaissance_text_records(html: str) -> list[dict[str, Any]]:
    """Fallback léger pour Renaissance si la table est aplatie en texte.

    Le moteur de recherche expose parfois le contenu sous forme de texte plutôt
    que comme une vraie table. Cette fonction récupère les lignes les plus
    structurées sans prétendre remplacer une API.
    """
    text = _strip_html(html)
    # Exemple observé : "MOT MetaOptics MOT 00/00/00 3.0 $5.00 - $7.00 $18 Roth".
    pattern = re.compile(
        r"\b(?P<ticker>[A-Z][A-Z0-9.]{1,8})\s+"
        r"(?P<company>[A-Z][A-Za-z0-9&.,'’‑–—() /-]{2,80}?)\s+"
        r"(?P=ticker)\s+"
        r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4}|00/00/00|TBA|TBD)\s+"
        r"(?P<shares>[-\d.]+)?\s*"
        r"(?P<price>\$?\d+(?:\.\d+)?(?:\s*-\s*\$?\d+(?:\.\d+)?)?)?",
        flags=re.IGNORECASE,
    )
    records: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        company = match.group("company").strip()
        if len(company) < 3 or company.lower() in {"company", "ticker"}:
            continue
        records.append(
            {
                "Symbole": match.group("ticker"),
                "Société": company,
                "Date": match.group("date"),
                "Actions offertes": match.group("shares") or "",
                "Prix indicatif": match.group("price") or "",
                "Statut": "À venir",
            }
        )
    return records


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
        "expected to trade": "Date",
        "trade date": "Date",
        "offer date": "Date",
        "pricing date": "Date",
        "filing date": "Date",
        "price date": "Date",
        "exchange": "Bourse",
        "market": "Bourse",
        "country": "Pays",
        "nation": "Pays",
        "event type": "Type d’événement",
        "event": "Type d’événement",
        "ipo stage": "Type d’événement",
        "price": "Prix indicatif",
        "price range": "Prix indicatif",
        "price low": "Prix indicatif",
        "price high": "Prix indicatif",
        "range": "Prix indicatif",
        "shares": "Actions offertes",
        "shares offered": "Actions offertes",
        "shares (m)": "Actions offertes",
        "shares millions": "Actions offertes",
        "offer amount": "Actions offertes",
        "est. $ volume": "Montant estimé",
        "deal size ($m)": "Montant estimé",
        "deal size": "Montant estimé",
        "proceeds": "Montant estimé",
        "amount": "Montant estimé",
        "size": "Montant estimé",
        "status": "Statut",
        "scoop rating": "Statut",
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
        if not exchange and source in {"Nasdaq", "NYSE"}:
            exchange = source.upper()
        country = _first_value(
            record,
            (
                "Pays",
                "country",
                "Country",
                "nation",
                "Nation",
                "region",
            ),
        )
        event_type = _first_value(
            record,
            (
                "Type d’événement",
                "Type d'événement",
                "eventType",
                "event_type",
                "event",
                "type",
                "IPO Stage",
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
                "Price Low",
                "priceLow",
                "low",
                "proposedSharePrice",
                "offerPrice",
                "ipoPrice",
                "expectedPrice",
                "sharePrice",
            ),
        )
        price_high = _first_value(record, ("Price High", "priceHigh", "high"))
        if price and price_high and str(price_high).strip() not in str(price):
            price = f"{price}-{price_high}"
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
        amount = _first_value(
            record,
            (
                "Montant estimé",
                "Deal Size",
                "Deal Size ($M)",
                "dealSize",
                "proceeds",
                "Proceeds",
                "amount",
                "Amount",
                "Est. $ Volume",
                "marketCap",
            ),
        )
        status = _first_value(record, ("Statut", "status", "Status", "dealStatus", "eventType", "type"))
        link = _first_value(record, ("Lien", "url", "link", "prospectusUrl", "filingUrl", "webUrl", "Filing", "Prospectus"))

        if not company and not symbol:
            continue

        rows.append(
            {
                "Date": _format_date(ipo_date),
                "Société": _clean_text(company),
                "Symbole": _clean_text(symbol).upper(),
                "Bourse": _clean_text(exchange).upper(),
                "Pays": _normalise_country(country, exchange, source),
                "Type d’événement": _normalise_event_type(event_type, status, source),
                "Prix indicatif": _clean_text(price),
                "Actions offertes": _clean_text(shares),
                "Montant estimé": _clean_text(amount),
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
    pipeline_start_ts = start_ts - pd.Timedelta(days=180)
    dated = work["DateTri"].notna()
    event_text = (
        work.get("Type d’événement", pd.Series("", index=work.index))
        .fillna("")
        .astype(str)
        .str.lower()
    )
    status_text = work.get("Statut", pd.Series("", index=work.index)).fillna("").astype(str).str.lower()
    is_pipeline = (
        event_text.str.contains("dépôt|depot|filing|réglementaire|reglementaire|nouvelle inscription", regex=True)
        | status_text.str.contains("dossier|filed|filing|s-1|f-1|nouvelle inscription", regex=True)
    )
    calendar_range = (work["DateTri"] >= start_ts) & (work["DateTri"] <= end_ts)
    pipeline_range = (work["DateTri"] >= pipeline_start_ts) & (work["DateTri"] <= end_ts)
    unknown_date = ~dated & work["Société"].ne("")
    return work.loc[(dated & calendar_range) | (is_pipeline & dated & pipeline_range) | unknown_date].copy()


def _deduplicate(frame: pd.DataFrame) -> pd.DataFrame:
    """Fusionne les doublons entre sources au lieu de les afficher plusieurs fois.

    En plus de la clé exacte, cette version détecte les doublons probables par
    symbole et par similarité de nom. Cela évite les répétitions du type
    "Ltd." / "Limited", accentuation, ponctuation ou petits écarts entre sites.
    """
    if frame.empty:
        return frame

    work = frame.copy()
    work["_source_rank"] = work["Source"].map(lambda value: SOURCE_PRIORITY.get(str(value), 50))
    work["_complete_rank"] = work.apply(_row_completeness, axis=1)
    work = work.sort_values(["_source_rank", "_complete_rank"], ascending=[True, False])

    groups: list[list[pd.Series]] = []
    for _, row in work.iterrows():
        placed = False
        for group in groups:
            if any(_rows_are_probable_duplicate(row, candidate) for candidate in group):
                group.append(row)
                placed = True
                break
        if not placed:
            groups.append([row])

    merged_rows: list[dict[str, Any]] = []
    for group in groups:
        group_frame = pd.DataFrame(group).drop(columns=["_source_rank", "_complete_rank"], errors="ignore")
        merged_rows.append(_merge_duplicate_group(group_frame))
    return pd.DataFrame(merged_rows)


def _dedupe_key(row: pd.Series) -> str:
    # Le nom passe avant le symbole afin de fusionner les cas où une source
    # publie déjà le ticker et une autre indique seulement le nom de la société.
    name_key = _normalise_company_key(row.get("Société", ""))
    if name_key:
        return f"name:{name_key}"
    symbol_key = _normalise_symbol_key(row.get("Symbole", ""))
    return f"symbol:{symbol_key}" if symbol_key else ""


def _rows_are_probable_duplicate(left: pd.Series, right: pd.Series) -> bool:
    left_symbol = _normalise_symbol_key(left.get("Symbole", ""))
    right_symbol = _normalise_symbol_key(right.get("Symbole", ""))
    if left_symbol and right_symbol and left_symbol == right_symbol:
        return True

    left_name = _normalise_company_key(left.get("Société", ""))
    right_name = _normalise_company_key(right.get("Société", ""))
    if not left_name or not right_name:
        return False
    if left_name == right_name:
        return True
    if len(left_name) >= 8 and len(right_name) >= 8 and (left_name in right_name or right_name in left_name):
        return True
    return SequenceMatcher(None, left_name, right_name).ratio() >= 0.91


def _merge_duplicate_group(group: pd.DataFrame) -> dict[str, Any]:
    ranked = group.copy()
    ranked["_source_rank"] = ranked["Source"].map(lambda value: SOURCE_PRIORITY.get(str(value), 50))
    ranked["_dated_rank"] = pd.to_datetime(ranked["Date"], errors="coerce").notna().astype(int)
    ranked["_complete_rank"] = ranked.apply(_row_completeness, axis=1)
    ranked = ranked.sort_values(
        ["_source_rank", "_dated_rank", "_complete_rank"],
        ascending=[True, False, False],
    )

    base = ranked.iloc[0].drop(labels=["_source_rank", "_dated_rank", "_complete_rank"], errors="ignore").to_dict()
    for _, row in ranked.iterrows():
        for column in IPO_COLUMNS:
            candidate = _clean_text(row.get(column, ""))
            current = _clean_text(base.get(column, ""))
            if column == "Source":
                continue
            if _is_missing_value(current) and not _is_missing_value(candidate):
                base[column] = candidate

        # Si la ligne prioritaire n'a pas de date ferme mais qu'une autre source
        # en a une, on utilise la date ferme.
        current_date = _parse_date(base.get("Date", ""))
        candidate_date = _parse_date(row.get("Date", ""))
        if current_date is None and candidate_date is not None:
            base["Date"] = _format_date(candidate_date)

    sources = []
    for source in ranked.sort_values("_source_rank")["Source"].astype(str).tolist():
        if source and source not in sources:
            sources.append(source)
    base["Source"] = " + ".join(sources)
    return base


def _row_completeness(row: pd.Series) -> int:
    useful_columns = [
        "Date",
        "Société",
        "Symbole",
        "Bourse",
        "Pays",
        "Type d’événement",
        "Prix indicatif",
        "Actions offertes",
        "Montant estimé",
        "Statut",
        "Lien",
    ]
    return sum(0 if _is_missing_value(row.get(column, "")) else 1 for column in useful_columns)


def _is_missing_value(value: Any) -> bool:
    text = _clean_text(value)
    return text == "" or text.lower() in {"à confirmer", "a confirmer", "n/d", "n/a", "none", "nan", "-"}


def _normalise_symbol_key(value: Any) -> str:
    text = _clean_text(value).upper()
    text = re.sub(r"[^A-Z0-9]", "", text)
    # Uniformise VII.U / VIIU sans confondre les tickers vides ou trop courts.
    return text if len(text) >= 2 else ""


def _normalise_company_key(value: Any) -> str:
    text = _clean_text(value).lower()
    text = unescape(text)
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    words = [word for word in text.split() if word not in {
        "inc", "corp", "corporation", "company", "co", "ltd", "limited",
        "plc", "llc", "group", "holdings", "holding", "sa", "spa", "ag",
        "nv", "se", "lp", "class", "ordinary", "shares", "common",
    }]
    return " ".join(words).strip()


def _add_timing_columns(frame: pd.DataFrame, today: date) -> pd.DataFrame:
    if frame.empty:
        return _empty_frame()
    work = frame.copy()
    days: list[Any] = []
    moments: list[str] = []
    event_values = work.get("Type d’événement", pd.Series("", index=work.index)).fillna("").astype(str).tolist()
    for idx, value in enumerate(work.get("DateTri", [])):
        event_text = event_values[idx].lower() if idx < len(event_values) else ""
        is_pipeline = any(token in event_text for token in ("dépôt", "depot", "filing", "réglementaire", "reglementaire", "nouvelle inscription"))
        if pd.isna(value):
            days.append(pd.NA)
            moments.append("Pipeline à confirmer" if is_pipeline else "Date à confirmer")
            continue
        if is_pipeline:
            days.append(pd.NA)
            moments.append("Pipeline récent")
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


def _add_quality_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty_frame()
    work = frame.copy()
    counts: list[int] = []
    scores: list[int] = []
    labels: list[str] = []
    maturity: list[str] = []
    gaps: list[str] = []
    for _, row in work.iterrows():
        sources = _split_sources(row.get("Source", ""))
        source_count = max(1, len(sources))
        counts.append(source_count)

        score = 35
        if source_count >= 2:
            score += 20
        if source_count >= 3:
            score += 10
        if any(source in {"Fichier local", "Finnhub", "Financial Modeling Prep"} for source in sources):
            score += 15
        if _parse_date(row.get("Date", "")) is not None and "pipeline" not in _clean_text(row.get("Moment", "")).lower():
            score += 15
        if not _is_missing_value(row.get("Symbole", "")):
            score += 5
        if not _is_missing_value(row.get("Prix indicatif", "")) or not _is_missing_value(row.get("Montant estimé", "")):
            score += 5
        score = max(0, min(100, score))
        scores.append(score)
        if score >= 80:
            labels.append("Élevée")
        elif score >= 60:
            labels.append("Moyenne")
        else:
            labels.append("Indicative")

        event_text = _clean_text(row.get("Type d’événement", "")).lower()
        has_date = _parse_date(row.get("Date", "")) is not None
        has_price = not _is_missing_value(row.get("Prix indicatif", ""))
        if any(token in event_text for token in ("dépôt", "depot", "filing", "réglementaire", "reglementaire")):
            maturity.append("Dossier déposé")
        elif has_date and has_price:
            maturity.append("Fourchette annoncée")
        elif has_date:
            maturity.append("Date annoncée")
        else:
            maturity.append("À confirmer")

        missing = []
        if not has_date:
            missing.append("date")
        if _is_missing_value(row.get("Symbole", "")):
            missing.append("symbole")
        if _is_missing_value(row.get("Prix indicatif", "")) and _is_missing_value(row.get("Montant estimé", "")):
            missing.append("prix/montant")
        gaps.append("Complet" if not missing else "À vérifier : " + ", ".join(missing))

    work["Sources détectées"] = counts
    work["Score donnée"] = scores
    work["Confiance donnée"] = labels
    work["Maturité IPO"] = maturity
    work["Points à vérifier"] = gaps
    return work


def _split_sources(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    return [part.strip() for part in text.split("+") if part.strip()]


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


def _normalise_country(country: Any, exchange: Any, source: str) -> str:
    text = _clean_text(country)
    if text:
        return text
    exchange_text = _clean_text(exchange).upper()
    source_text = _clean_text(source).lower()
    if any(token in exchange_text for token in ("TSX", "TSXV", "NEO", "CSE")) or "tmx" in source_text:
        return "Canada"
    if any(token in exchange_text for token in ("NASDAQ", "NYSE", "AMEX")) or "sec edgar" in source_text:
        return "États-Unis"
    return ""


def _normalise_event_type(event_type: Any, status: Any, source: str) -> str:
    text = _clean_text(event_type)
    lowered = (text + " " + _clean_text(status) + " " + source).lower()
    if any(token in lowered for token in ("s-1", "f-1", "filing", "filed", "dossier", "dépôt", "depot", "sec edgar")):
        return "Dépôt réglementaire"
    if "tmx" in lowered or "new listing" in lowered or "nouvelle inscription" in lowered:
        return "Nouvelle inscription"
    if text:
        return text
    return "Calendrier IPO"


def _normalise_status(value: Any) -> str:
    status = _clean_text(value)
    if not status:
        return "À venir"
    lowered = status.lower()
    if "expected" in lowered or "upcoming" in lowered or "pricing" in lowered:
        return "À venir"
    if "priced" in lowered:
        return "Prix fixé"
    if "s-1" in lowered or "f-1" in lowered or "filed" in lowered or "filing" in lowered or "file" in lowered or "dossier" in lowered:
        return "Dossier déposé"
    if "new listing" in lowered or "nouvelle inscription" in lowered:
        return "Nouvelle inscription"
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
            + ". Les doublons entre sources sont fusionnés automatiquement. "
            "Les sources publiques sans API sont utiles pour la veille, mais ne garantissent pas une couverture complète."
        )
    return "Aucune source IPO active pour l'instant. Ajoute un fichier local ou une clé API pour fiabiliser la couverture."
