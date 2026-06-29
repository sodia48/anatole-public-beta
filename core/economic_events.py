from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


TORONTO_TZ = ZoneInfo("America/Toronto")
UTC_TZ = ZoneInfo("UTC")

STATCAN_CALENDAR_URL = (
    "https://www150.statcan.gc.ca/n1/dai-quo/ssi/homepage/"
    "schedule-key_indicators-fra.json"
)
BANK_OF_CANADA_RSS_URL = (
    "https://www.bankofcanada.ca/content_type/upcoming-events/feed/"
)
BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BLS_YEAR_CALENDAR_URL = "https://www.bls.gov/schedule/{year}/home.htm"
BEA_RELEASES_JSON_URL = "https://apps.bea.gov/API/signup/release_dates.json"
FED_FOMC_CALENDAR_URL = (
    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
)

SOURCE_ORDER = {
    "Banque du Canada": 0,
    "Statistique Canada": 1,
    "Réserve fédérale": 2,
    "BLS": 3,
    "BEA": 4,
}

DEFAULT_COUNTRIES = ["Canada", "États-Unis"]

DISPLAY_COLUMNS = [
    "Date",
    "Heure",
    "Importance",
    "Pays",
    "Devise",
    "Catégorie",
    "Événement",
    "Description",
    "Source",
    "Lien",
]

MONTHS_EN = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

KEYWORD_RULES: list[tuple[tuple[str, ...], str, int]] = [
    (
        (
            "interest rate announcement",
            "interest rate decision",
            "policy rate",
            "fomc meeting",
            "fomc decision",
            "taux directeur",
            "annonce du taux",
            "décision de taux",
            "monetary policy report",
            "rapport sur la politique monétaire",
        ),
        "Banque centrale",
        100,
    ),
    (
        (
            "consumer price index",
            "indice des prix à la consommation",
            "inflation",
            "core pce",
            "personal income and outlays",
            "pce",
        ),
        "Inflation",
        95,
    ),
    (
        (
            "employment situation",
            "labour force survey",
            "enquête sur la population active",
            "nonfarm payroll",
            "unemployment",
            "emploi",
            "chômage",
        ),
        "Emploi",
        95,
    ),
    (
        (
            "gross domestic product",
            "produit intérieur brut",
            "gdp",
            "pib",
        ),
        "PIB",
        93,
    ),
    (
        (
            "producer price index",
            "indice des prix des produits industriels",
            "ppi",
        ),
        "Inflation",
        82,
    ),
    (
        (
            "job openings and labor turnover",
            "jolts",
            "employment cost index",
            "coût de l'emploi",
            "real earnings",
        ),
        "Emploi",
        80,
    ),
    (
        (
            "retail trade",
            "retail sales",
            "commerce de détail",
            "ventes au détail",
        ),
        "Consommation",
        82,
    ),
    (
        (
            "business outlook survey",
            "enquête sur les perspectives des entreprises",
            "consumer expectations",
            "attentes des consommateurs",
            "market participants survey",
            "enquête auprès des participants au marché",
        ),
        "Enquêtes",
        78,
    ),
    (
        (
            "international trade",
            "commerce international",
            "merchandise trade",
            "trade in goods and services",
        ),
        "Commerce",
        75,
    ),
    (
        (
            "summary of deliberations",
            "résumé des délibérations",
            "fomc minutes",
            "minutes",
        ),
        "Banque centrale",
        78,
    ),
    (
        (
            "building permits",
            "permis de bâtir",
            "housing",
            "new housing price",
            "prix des logements",
        ),
        "Immobilier",
        65,
    ),
    (
        (
            "industrial production",
            "manufacturing",
            "fabrication",
            "productivity and costs",
            "productivité",
        ),
        "Activité",
        67,
    ),
]

BLS_ESSENTIAL_PATTERNS = (
    "Employment Situation",
    "Consumer Price Index",
    "Producer Price Index",
    "Job Openings and Labor Turnover",
    "Employment Cost Index",
    "Productivity and Costs",
    "Real Earnings",
    "Import and Export Price Indexes",
)

BEA_ESSENTIAL_RELEASES = (
    "Gross Domestic Product",
    "Personal Income and Outlays",
    "U.S. International Trade in Goods and Services",
)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "text/calendar;q=0.8,*/*;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9,fr-CA;q=0.8",
        "Cache-Control": "no-cache",
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _event_category_score(
    title: str,
    source: str,
    country: str,
) -> tuple[str, int]:
    lowered = _clean_text(title).lower()
    category = "Autre"
    score = 48

    for keywords, candidate_category, candidate_score in KEYWORD_RULES:
        if any(keyword in lowered for keyword in keywords):
            if candidate_score > score:
                category = candidate_category
                score = candidate_score

    if source == "Banque du Canada":
        score = max(score, 70)
    elif source == "Statistique Canada":
        score = max(score, 58)
    elif source == "Réserve fédérale":
        category = "Banque centrale"
        score = max(score, 100)
    elif source in {"BLS", "BEA"}:
        score = max(score, 62)

    if country == "Canada":
        score = min(100, score + 3)

    return category, min(score, 100)


def _importance_label(score: int) -> str:
    if score >= 90:
        return "Très élevée"
    if score >= 75:
        return "Élevée"
    if score >= 55:
        return "Moyenne"
    return "Faible"


def _make_record(
    *,
    timestamp: pd.Timestamp | datetime,
    title: str,
    source: str,
    country: str,
    currency: str,
    description: str = "",
    url: str = "",
    category: str | None = None,
    score: int | None = None,
) -> dict[str, Any]:
    ts = pd.Timestamp(timestamp)

    if ts.tzinfo is None:
        ts = ts.tz_localize(TORONTO_TZ)
    else:
        ts = ts.tz_convert(TORONTO_TZ)

    inferred_category, inferred_score = _event_category_score(
        title,
        source,
        country,
    )
    final_category = category or inferred_category
    final_score = int(score if score is not None else inferred_score)

    return {
        "Date": ts.strftime("%Y-%m-%d"),
        "Heure": ts.strftime("%H:%M"),
        "DateTime": ts.tz_localize(None),
        "Pays": country,
        "Devise": currency,
        "Catégorie": final_category,
        "Événement": _clean_text(title),
        "Description": _clean_text(description),
        "ImportanceScore": final_score,
        "Importance": _importance_label(final_score),
        "Source": source,
        "Lien": url,
    }


def _between_dates(
    frame: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if frame.empty:
        return frame

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize() + pd.Timedelta(days=1)
    return frame[
        (frame["DateTime"] >= start)
        & (frame["DateTime"] < end)
    ].copy()


def _translate_boc_title(title: str) -> str:
    translations = {
        "Interest Rate Announcement and Monetary Policy Report":
            "Annonce du taux directeur et Rapport sur la politique monétaire",
        "Interest Rate Announcement":
            "Annonce du taux directeur",
        "Publication: Summary of Deliberations":
            "Publication : Résumé des délibérations",
        "Release: Business Outlook Survey and Canadian Survey of Consumer Expectations":
            "Publication : Enquête sur les perspectives des entreprises et attentes des consommateurs",
        "Release: Market Participants Survey":
            "Publication : Enquête auprès des participants au marché",
        "Release of the Financial Stability Report":
            "Publication du Rapport sur la stabilité financière",
    }
    clean = _clean_text(title)
    return translations.get(clean, clean)


def _translate_us_title(title: str) -> str:
    clean = _clean_text(title)
    replacements = [
        ("Employment Situation", "Situation de l'emploi (Nonfarm Payrolls)"),
        ("Consumer Price Index", "Indice des prix à la consommation (CPI)"),
        ("Producer Price Index", "Indice des prix à la production (PPI)"),
        (
            "Job Openings and Labor Turnover Survey",
            "Enquête JOLTS sur les offres d'emploi",
        ),
        ("Employment Cost Index", "Indice du coût de l'emploi"),
        ("Productivity and Costs", "Productivité et coûts"),
        ("Real Earnings", "Salaires réels"),
        (
            "U.S. Import and Export Price Indexes",
            "Prix américains à l'importation et à l'exportation",
        ),
        ("Gross Domestic Product", "Produit intérieur brut (PIB)"),
        (
            "Personal Income and Outlays",
            "Revenus et dépenses personnels (PCE)",
        ),
        (
            "U.S. International Trade in Goods and Services",
            "Commerce international américain",
        ),
    ]
    for original, translated in replacements:
        if clean.startswith(original):
            return clean.replace(original, translated, 1)
    return clean


def _parse_statcan_payload(payload: Any) -> pd.DataFrame:
    if not isinstance(payload, list):
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        raw_date = item.get("date")
        parsed = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(parsed):
            continue

        event_date = parsed.date()
        timestamp = pd.Timestamp(
            datetime.combine(event_date, time(8, 30)),
            tz=TORONTO_TZ,
        )

        raw_url = str(item.get("url") or "")
        if raw_url.startswith("//"):
            url = "https:" + raw_url
        elif raw_url:
            url = urljoin("https://www.statcan.gc.ca/", raw_url)
        else:
            url = "https://www150.statcan.gc.ca/n1/dai-quo/index-fra.htm"

        records.append(
            _make_record(
                timestamp=timestamp,
                title=item.get("title") or "Publication économique",
                source="Statistique Canada",
                country="Canada",
                currency="CAD",
                description=item.get("description") or "",
                url=url,
            )
        )

    return pd.DataFrame(records)


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_statcan_calendar() -> tuple[pd.DataFrame, str]:
    try:
        response = requests.get(
            STATCAN_CALENDAR_URL,
            headers=_headers(),
            timeout=12,
        )
        response.raise_for_status()
        return _parse_statcan_payload(response.json()), ""
    except Exception as exc:
        return pd.DataFrame(), (
            f"Statistique Canada : {type(exc).__name__}: {exc}"
        )


def _find_xml_text(item: ET.Element, local_name: str) -> str:
    for child in list(item):
        tag = child.tag.split("}")[-1]
        if tag == local_name:
            return child.text or ""
    return ""


def _parse_boc_rss(xml_text: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    records: list[dict[str, Any]] = []

    for item in root.findall(".//item"):
        title = _find_xml_text(item, "title")
        link = _find_xml_text(item, "link")
        description = _find_xml_text(item, "description")
        date_text = (
            _find_xml_text(item, "pubDate")
            or _find_xml_text(item, "date")
        )

        if not title or not date_text:
            continue

        try:
            parsed_date = parsedate_to_datetime(date_text)
        except (TypeError, ValueError):
            parsed = pd.to_datetime(date_text, errors="coerce", utc=True)
            if pd.isna(parsed):
                continue
            parsed_date = parsed.to_pydatetime()

        timestamp = pd.Timestamp(parsed_date)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(TORONTO_TZ)
        else:
            timestamp = timestamp.tz_convert(TORONTO_TZ)

        combined_text = f"{title} {description}"
        time_match = re.search(
            r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(?:\(ET\)|ET)\b",
            combined_text,
            flags=re.IGNORECASE,
        )
        if time_match:
            timestamp = timestamp.replace(
                hour=int(time_match.group(1)),
                minute=int(time_match.group(2)),
                second=0,
            )

        translated_title = _translate_boc_title(title)
        records.append(
            _make_record(
                timestamp=timestamp,
                title=translated_title,
                source="Banque du Canada",
                country="Canada",
                currency="CAD",
                description=description,
                url=link or "https://www.bankofcanada.ca/press/upcoming-events/",
            )
        )

    return pd.DataFrame(records)


@st.cache_data(ttl=3_600, show_spinner=False)
def fetch_bank_of_canada_calendar() -> tuple[pd.DataFrame, str]:
    try:
        response = requests.get(
            BANK_OF_CANADA_RSS_URL,
            headers=_headers(),
            timeout=12,
        )
        response.raise_for_status()
        return _parse_boc_rss(response.text), ""
    except Exception as exc:
        return pd.DataFrame(), (
            f"Banque du Canada : {type(exc).__name__}: {exc}"
        )


def _unfold_ics_lines(text: str) -> list[str]:
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []

    for line in raw_lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    return unfolded


def _decode_ics_text(value: str) -> str:
    return (
        value.replace(r"\n", " ")
        .replace(r"\N", " ")
        .replace(r"\,", ",")
        .replace(r"\;", ";")
        .replace(r"\\", "\\")
        .strip()
    )


def _parse_ics_datetime(property_name: str, value: str) -> pd.Timestamp | None:
    cleaned = value.strip()

    try:
        if cleaned.endswith("Z"):
            return pd.Timestamp(
                datetime.strptime(cleaned, "%Y%m%dT%H%M%SZ"),
                tz=UTC_TZ,
            ).tz_convert(TORONTO_TZ)

        if "VALUE=DATE" in property_name and "T" not in cleaned:
            parsed_date = datetime.strptime(cleaned, "%Y%m%d").date()
            return pd.Timestamp(
                datetime.combine(parsed_date, time(8, 30)),
                tz=TORONTO_TZ,
            )

        parsed = pd.Timestamp(datetime.strptime(cleaned, "%Y%m%dT%H%M%S"))
        if "TZID=" in property_name:
            timezone_name = property_name.split("TZID=", 1)[1].split(";", 1)[0]
            try:
                return parsed.tz_localize(ZoneInfo(timezone_name)).tz_convert(
                    TORONTO_TZ
                )
            except Exception:
                pass

        return parsed.tz_localize(TORONTO_TZ)
    except (TypeError, ValueError):
        return None


def _parse_bls_ics(text: str) -> pd.DataFrame:
    lines = _unfold_ics_lines(text)
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        current[key] = value

    records: list[dict[str, Any]] = []
    for event in events:
        summary_key = next(
            (key for key in event if key.startswith("SUMMARY")),
            None,
        )
        dt_key = next(
            (key for key in event if key.startswith("DTSTART")),
            None,
        )
        if not summary_key or not dt_key:
            continue

        original_title = _decode_ics_text(event[summary_key])
        if not any(
            pattern.lower() in original_title.lower()
            for pattern in BLS_ESSENTIAL_PATTERNS
        ):
            continue

        timestamp = _parse_ics_datetime(dt_key, event[dt_key])
        if timestamp is None:
            continue

        url_key = next(
            (key for key in event if key.startswith("URL")),
            None,
        )
        url = (
            _decode_ics_text(event[url_key])
            if url_key
            else "https://www.bls.gov/schedule/"
        )

        records.append(
            _make_record(
                timestamp=timestamp,
                title=_translate_us_title(original_title),
                source="BLS",
                country="États-Unis",
                currency="USD",
                description="Publication officielle du Bureau of Labor Statistics.",
                url=url,
            )
        )

    return pd.DataFrame(records)



class _BLSTableParser(HTMLParser):
    """Extracteur minimal des lignes de tableaux du calendrier BLS."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if lowered == "tr":
            self._in_row = True
            self._current_row = []
        elif lowered in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if lowered in {"td", "th"} and self._in_cell:
            text = _clean_text(" ".join(self._current_cell))
            self._current_row.append(text)
            self._current_cell = []
            self._in_cell = False
        elif lowered == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = []
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._in_cell and not self._skip_depth:
            self._current_cell.append(data)


_BLS_DATE_PATTERN = re.compile(
    r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"[A-Za-z]+\s+\d{1,2}(?:,\s+\d{4})?$",
    flags=re.IGNORECASE,
)
_BLS_TIME_PATTERN = re.compile(
    r"^\d{1,2}:\d{2}\s*(?:AM|PM)$",
    flags=re.IGNORECASE,
)


def _parse_bls_html(html_text: str, year: int) -> pd.DataFrame:
    parser = _BLSTableParser()
    parser.feed(html_text)

    records: list[dict[str, Any]] = []
    last_event_date = None

    for raw_cells in parser.rows:
        cells = [_clean_text(cell) for cell in raw_cells if _clean_text(cell)]
        if not cells:
            continue

        date_index = next(
            (
                index
                for index, cell in enumerate(cells)
                if _BLS_DATE_PATTERN.match(cell)
            ),
            None,
        )
        time_index = next(
            (
                index
                for index, cell in enumerate(cells)
                if _BLS_TIME_PATTERN.match(cell)
            ),
            None,
        )

        if date_index is not None:
            date_text = cells[date_index]
            if not re.search(r"\b\d{4}\b", date_text):
                date_text = f"{date_text}, {year}"
            parsed_date = pd.to_datetime(date_text, errors="coerce")
            if pd.notna(parsed_date):
                last_event_date = parsed_date.date()

        if last_event_date is None or time_index is None:
            continue

        title_candidates = [
            cell
            for index, cell in enumerate(cells)
            if index not in {date_index, time_index}
        ]
        if not title_candidates:
            continue

        original_title = max(title_candidates, key=len)
        if not any(
            pattern.lower() in original_title.lower()
            for pattern in BLS_ESSENTIAL_PATTERNS
        ):
            continue

        parsed_time = datetime.strptime(
            cells[time_index].upper(),
            "%I:%M %p",
        ).time()
        timestamp = pd.Timestamp(
            datetime.combine(last_event_date, parsed_time),
            tz=TORONTO_TZ,
        )

        records.append(
            _make_record(
                timestamp=timestamp,
                title=_translate_us_title(original_title),
                source="BLS",
                country="États-Unis",
                currency="USD",
                description=(
                    "Publication officielle du Bureau of Labor Statistics."
                ),
                url=BLS_YEAR_CALENDAR_URL.format(year=year),
            )
        )

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame

    return frame.drop_duplicates(
        subset=["DateTime", "Événement", "Source"],
        keep="first",
    )


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_bls_calendar(
    start_year: int | None = None,
    end_year: int | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Essaie d'abord le calendrier ICS du BLS. Si le serveur bloque l'ICS,
    Anatole se rabat automatiquement sur les pages HTML officielles.
    """

    try:
        response = requests.get(
            BLS_ICS_URL,
            headers=_headers(),
            timeout=15,
        )
        response.raise_for_status()
        frame = _parse_bls_ics(response.text)
        if not frame.empty:
            return frame, ""
    except Exception:
        # Le BLS peut refuser le fichier ICS aux serveurs cloud.
        # Le calendrier HTML officiel est alors utilisé.
        pass

    current_year = datetime.now(TORONTO_TZ).year
    first_year = int(start_year or current_year)
    last_year = int(end_year or first_year)
    frames: list[pd.DataFrame] = []

    for year in range(first_year, last_year + 1):
        try:
            response = requests.get(
                BLS_YEAR_CALENDAR_URL.format(year=year),
                headers=_headers(),
                timeout=15,
            )
            response.raise_for_status()
            frame = _parse_bls_html(response.text, year)
            if not frame.empty:
                frames.append(frame)
        except Exception:
            continue

    if frames:
        return (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(
                subset=["DateTime", "Événement", "Source"],
                keep="first",
            ),
            "",
        )

    return pd.DataFrame(), "indisponible temporairement"


def _parse_bea_payload(payload: Any) -> pd.DataFrame:
    if not isinstance(payload, dict):
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for release_name in BEA_ESSENTIAL_RELEASES:
        release_info = payload.get(release_name)
        if not isinstance(release_info, dict):
            continue

        dates = release_info.get("release_dates", [])
        if not isinstance(dates, list):
            continue

        for date_value in dates:
            timestamp = pd.to_datetime(
                date_value,
                errors="coerce",
                utc=True,
            )
            if pd.isna(timestamp):
                continue

            records.append(
                _make_record(
                    timestamp=timestamp,
                    title=_translate_us_title(release_name),
                    source="BEA",
                    country="États-Unis",
                    currency="USD",
                    description="Publication officielle du Bureau of Economic Analysis.",
                    url="https://www.bea.gov/news/schedule",
                )
            )

    return pd.DataFrame(records)


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_bea_calendar() -> tuple[pd.DataFrame, str]:
    try:
        response = requests.get(
            BEA_RELEASES_JSON_URL,
            headers=_headers(),
            timeout=12,
        )
        response.raise_for_status()
        return _parse_bea_payload(response.json()), ""
    except Exception as exc:
        return pd.DataFrame(), f"BEA : {type(exc).__name__}: {exc}"


def _parse_fomc_html(
    html_text: str,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    without_scripts = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    without_styles = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        without_scripts,
        flags=re.IGNORECASE | re.DOTALL,
    )
    plain = unescape(re.sub(r"<[^>]+>", "\n", without_styles))
    plain = re.sub(r"[ \t]+", " ", plain)
    plain = re.sub(r"\n\s*\n+", "\n", plain)

    records: list[dict[str, Any]] = []

    for year in range(start_year, end_year + 1):
        marker = f"{year} FOMC Meetings"
        start_index = plain.find(marker)
        if start_index < 0:
            continue

        remaining = plain[start_index + len(marker):]
        next_heading = re.search(r"\b\d{4} FOMC Meetings\b", remaining)
        section = (
            remaining[:next_heading.start()]
            if next_heading
            else remaining
        )

        for month_name, month_number in MONTHS_EN.items():
            match = re.search(
                rf"\b{month_name}\b\s+"
                r"(\d{1,2})"
                r"(?:\s*[-–]\s*(\d{1,2}))?"
                r"(\*)?",
                section,
                flags=re.IGNORECASE,
            )
            if not match:
                continue

            first_day = int(match.group(1))
            decision_day = int(match.group(2) or match.group(1))
            has_projections = bool(match.group(3))

            try:
                timestamp = pd.Timestamp(
                    datetime(
                        year,
                        month_number,
                        decision_day,
                        14,
                        0,
                    ),
                    tz=TORONTO_TZ,
                )
            except ValueError:
                continue

            description = (
                f"Réunion du FOMC les {first_day}"
                + (
                    f" et {decision_day}"
                    if decision_day != first_day
                    else ""
                )
                + ". Décision attendue à 14 h (heure de l'Est)."
            )
            if has_projections:
                description += (
                    " Réunion accompagnée des projections économiques."
                )

            records.append(
                _make_record(
                    timestamp=timestamp,
                    title="Décision de taux de la Réserve fédérale (FOMC)",
                    source="Réserve fédérale",
                    country="États-Unis",
                    currency="USD",
                    description=description,
                    url=FED_FOMC_CALENDAR_URL,
                    category="Banque centrale",
                    score=100,
                )
            )

    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    return frame.drop_duplicates(
        subset=["DateTime", "Événement", "Source"]
    )


@st.cache_data(ttl=43_200, show_spinner=False)
def fetch_fomc_calendar(
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, str]:
    try:
        response = requests.get(
            FED_FOMC_CALENDAR_URL,
            headers=_headers(),
            timeout=12,
        )
        response.raise_for_status()
        return _parse_fomc_html(
            response.text,
            start_year,
            end_year,
        ), ""
    except Exception as exc:
        return pd.DataFrame(), (
            f"Réserve fédérale : {type(exc).__name__}: {exc}"
        )


@st.cache_data(ttl=1_800, max_entries=16, show_spinner=False)
def fetch_official_economic_calendar(
    start_date: str,
    end_date: str,
    include_statcan: bool = True,
    include_boc: bool = True,
    include_bls: bool = True,
    include_bea: bool = True,
    include_fomc: bool = True,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Agrège les calendriers officiels en parallèle."""
    frames: list[pd.DataFrame] = []
    statuses: dict[str, str] = {}
    start_year = pd.Timestamp(start_date).year
    end_year = pd.Timestamp(end_date).year

    tasks: list[tuple[str, Any, tuple[Any, ...]]] = []
    if include_statcan:
        tasks.append((
            "Statistique Canada",
            fetch_statcan_calendar,
            (),
        ))
    if include_boc:
        tasks.append((
            "Banque du Canada",
            fetch_bank_of_canada_calendar,
            (),
        ))
    if include_bls:
        tasks.append((
            "BLS",
            fetch_bls_calendar,
            (start_year, end_year),
        ))
    if include_bea:
        tasks.append(("BEA", fetch_bea_calendar, ()))
    if include_fomc:
        tasks.append((
            "Réserve fédérale",
            fetch_fomc_calendar,
            (start_year, end_year),
        ))

    workers = min(5, max(1, len(tasks)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(function, *args): source_name
            for source_name, function, args in tasks
        }
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                frame, error = future.result()
            except Exception:
                frame, error = pd.DataFrame(), "indisponible temporairement"
            statuses[source_name] = error or "OK"
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                frames.append(frame)

    if not frames:
        return pd.DataFrame(), statuses

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = _between_dates(combined, start_date, end_date)
    if combined.empty:
        return combined, statuses

    combined["SourceOrdre"] = combined["Source"].map(
        SOURCE_ORDER
    ).fillna(99)
    combined = combined.sort_values(
        ["DateTime", "ImportanceScore", "SourceOrdre"],
        ascending=[True, False, True],
    )
    combined = combined.drop_duplicates(
        subset=["DateTime", "Événement", "Source"],
        keep="first",
    )
    return combined.reset_index(drop=True), statuses


def filter_economic_events(
    frame: pd.DataFrame,
    countries: list[str] | None = None,
    categories: list[str] | None = None,
    sources: list[str] | None = None,
    min_importance: str = "Moyenne",
    search: str = "",
) -> pd.DataFrame:
    if frame.empty:
        return frame

    result = frame.copy()

    if countries:
        result = result[result["Pays"].isin(countries)]
    if categories:
        result = result[result["Catégorie"].isin(categories)]
    if sources:
        result = result[result["Source"].isin(sources)]

    thresholds = {
        "Toutes": 0,
        "Faible": 0,
        "Moyenne": 55,
        "Élevée": 75,
        "Très élevée": 90,
    }
    result = result[
        result["ImportanceScore"]
        >= thresholds.get(min_importance, 55)
    ]

    if search.strip():
        needle = search.strip().lower()
        combined = (
            result["Événement"].astype(str)
            + " "
            + result["Description"].astype(str)
            + " "
            + result["Pays"].astype(str)
            + " "
            + result["Catégorie"].astype(str)
            + " "
            + result["Source"].astype(str)
        ).str.lower()
        result = result[
            combined.str.contains(
                needle,
                regex=False,
                na=False,
            )
        ]

    return result.sort_values(
        ["DateTime", "ImportanceScore"],
        ascending=[True, False],
    )


def importance_counts(frame: pd.DataFrame) -> dict[str, int]:
    labels = ["Très élevée", "Élevée", "Moyenne", "Faible"]
    if frame.empty or "Importance" not in frame:
        return {label: 0 for label in labels}
    counts = frame["Importance"].value_counts().to_dict()
    return {
        label: int(counts.get(label, 0))
        for label in labels
    }


def upcoming_highlights(
    frame: pd.DataFrame,
    limit: int = 8,
) -> pd.DataFrame:
    if frame.empty:
        return frame

    now = pd.Timestamp.now(tz=TORONTO_TZ).tz_localize(None)
    future = frame[frame["DateTime"] >= now].copy()
    if future.empty:
        future = frame.copy()

    return future.sort_values(
        ["ImportanceScore", "DateTime"],
        ascending=[False, True],
    ).head(limit)


def to_display_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    columns = [
        column
        for column in DISPLAY_COLUMNS
        if column in frame.columns
    ]
    return frame[columns].copy()
