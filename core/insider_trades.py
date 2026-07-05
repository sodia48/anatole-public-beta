from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
import math
import os
import re
from typing import Any, Iterable
from urllib.parse import quote_plus

import pandas as pd
import requests

CANONICAL_COLUMNS = [
    "Date",
    "Ticker",
    "Symbole Yahoo",
    "Société",
    "Insider",
    "Rôle",
    "Transaction",
    "Direction",
    "Actions",
    "Prix",
    "Valeur",
    "Source",
    "Lien",
]

SOURCE_COLUMNS = ["Source", "État", "Détail"]

DEFAULT_LOCAL_PATH = Path("data/insider_trades.csv")
DEFAULT_TIMEOUT = 10


# -----------------------------------------------------------------------------
# Normalisation générale
# -----------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    return text if text else default


def _as_float(value: Any) -> float:
    if value is None:
        return math.nan
    if isinstance(value, dict):
        value = value.get("raw", value.get("fmt"))
    try:
        text = str(value).replace("\u00a0", " ")
        text = text.replace("CAD", "").replace("CA$", "").replace("C$", "").replace("$", "")
        text = text.replace(",", "").strip()
        text = re.sub(r"[^0-9.\-]", "", text)
        if text in {"", "None", "nan", "NaN", ".", "-"}:
            return math.nan
        return float(text)
    except Exception:
        return math.nan


def _raw(value: Any) -> Any:
    if isinstance(value, dict):
        if "raw" in value:
            return value.get("raw")
        if "fmt" in value:
            return value.get("fmt")
    return value


def _as_date(value: Any) -> str:
    value = _raw(value)
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, (int, float)) and not math.isnan(float(value)):
            return datetime.fromtimestamp(float(value), timezone.utc).date().isoformat()
    except Exception:
        pass
    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=False)
        if pd.isna(parsed):
            return ""
        return parsed.date().isoformat()
    except Exception:
        return ""


def _normalise_company_for_slug(company: str) -> str:
    text = _as_text(company).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\b(incorporated|corporation|corp|inc|ltd|limited|plc|co|company|the)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def normalise_ticker(symbol: str) -> str:
    text = _as_text(symbol).upper()
    text = text.replace(".TO", "").replace("-TO", "")
    text = text.replace("/", ".").replace("-", ".")
    text = re.sub(r"[^A-Z0-9.]", "", text)
    return text


def to_yahoo_symbol(symbol: str) -> str:
    clean = normalise_ticker(symbol)
    if not clean:
        return ""
    return f"{clean}.TO"


def _direction_from_text(text: str, signed_change: float | None = None) -> str:
    if signed_change is not None and not math.isnan(signed_change):
        if signed_change > 0:
            return "Achat"
        if signed_change < 0:
            return "Vente"
    lowered = _as_text(text).lower()
    if any(token in lowered for token in ["buy", "purchase", "purchased", "acquisition", "achat", "acquired"]):
        return "Achat"
    if any(token in lowered for token in ["sale", "sell", "sold", "disposition", "vente", "disposed"]):
        return "Vente"
    if any(token in lowered for token in ["option", "grant", "award", "exercise", "exercice", "conversion"]):
        return "Options / rémunération"
    return "À classer"


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=CANONICAL_COLUMNS)


def _source_status(source: str, state: str, detail: str = "") -> dict[str, str]:
    return {"Source": source, "État": state, "Détail": detail}


# -----------------------------------------------------------------------------
# Liens externes
# -----------------------------------------------------------------------------

def sedi_issuer_search_url(company_or_symbol: str) -> str:
    # SEDI ne fournit pas de lien stable par émetteur sans identifiant interne.
    return "https://www.sedi.ca/sedi/SVTReportsAccessController?locale=en_CA"


def tmx_insider_url(symbol: str) -> str:
    clean = normalise_ticker(symbol)
    if clean:
        return f"https://money.tmx.com/en/quote/{quote_plus(clean)}/company"
    return "https://money.tmx.com/"


def yahoo_insider_url(symbol: str) -> str:
    yahoo = to_yahoo_symbol(symbol)
    if not yahoo:
        return ""
    return f"https://ca.finance.yahoo.com/quote/{quote_plus(yahoo)}/insider-transactions/"


def marketbeat_insider_url(symbol: str) -> str:
    clean = normalise_ticker(symbol)
    if not clean:
        return ""
    return f"https://www.marketbeat.com/stocks/TSE/{quote_plus(clean)}/insider-trades/"


def canadian_insider_url(symbol: str) -> str:
    clean = normalise_ticker(symbol)
    if not clean:
        return "https://m.canadianinsider.com/"
    return f"https://m.canadianinsider.com/node/7?ticker={quote_plus(clean)}"


def insiderscreener_company_url(symbol: str, company: str = "") -> str:
    slug = _normalise_company_for_slug(company)
    if slug:
        return f"https://www.insiderscreener.com/en/company/{quote_plus(slug)}"
    clean = normalise_ticker(symbol).lower()
    return f"https://www.insiderscreener.com/en/search?q={quote_plus(clean)}"


# -----------------------------------------------------------------------------
# Lecture locale / import contrôlé
# -----------------------------------------------------------------------------

def _canonicalise_frame(frame: pd.DataFrame, source: str = "Import interne") -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_frame()

    raw = frame.copy()
    lookup = {str(column).strip().lower(): column for column in raw.columns}

    def col(*names: str) -> str | None:
        keys = [name.strip().lower() for name in names]
        for key in keys:
            if key in lookup:
                return lookup[key]
        for key, original in lookup.items():
            if any(name in key for name in keys):
                return original
        return None

    ticker_col = col("ticker", "symbol", "symbole")
    if ticker_col is None:
        return _empty_frame()

    out = pd.DataFrame()
    out["Ticker"] = raw[ticker_col].map(normalise_ticker)
    out = out[out["Ticker"].astype(str).str.len() > 0].copy()
    out["Symbole Yahoo"] = out["Ticker"].map(to_yahoo_symbol)

    date_col = col("date", "transaction date", "filing date", "déclaration")
    out["Date"] = raw[date_col].map(_as_date) if date_col else ""

    company_col = col("société", "societe", "company", "issuer", "issuer name", "nom")
    insider_col = col("insider", "filer", "name", "initié", "initie")
    role_col = col("role", "rôle", "relation", "position", "title")
    trx_col = col("transaction", "type", "code", "description")
    shares_col = col("actions", "shares", "share", "securities", "quantity", "change")
    price_col = col("prix", "price", "transaction price")
    value_col = col("valeur", "value", "montant", "amount")
    source_col = col("source")
    link_col = col("lien", "link", "url")

    out["Société"] = raw[company_col].map(_as_text) if company_col else ""
    out["Insider"] = raw[insider_col].map(_as_text) if insider_col else ""
    out["Rôle"] = raw[role_col].map(_as_text) if role_col else ""
    out["Transaction"] = raw[trx_col].map(_as_text) if trx_col else ""
    out["Actions"] = raw[shares_col].map(_as_float) if shares_col else math.nan
    out["Prix"] = raw[price_col].map(_as_float) if price_col else math.nan
    out["Valeur"] = raw[value_col].map(_as_float) if value_col else math.nan

    missing_value = out["Valeur"].isna() & out["Actions"].notna() & out["Prix"].notna()
    out.loc[missing_value, "Valeur"] = (out.loc[missing_value, "Actions"].abs() * out.loc[missing_value, "Prix"]).round(2)

    out["Direction"] = [
        _direction_from_text(transaction, signed_change=shares if not pd.isna(shares) else None)
        for transaction, shares in zip(out["Transaction"], out["Actions"])
    ]
    out["Source"] = raw[source_col].map(_as_text) if source_col else source
    out["Lien"] = raw[link_col].map(_as_text) if link_col else out["Ticker"].map(yahoo_insider_url)

    return out[CANONICAL_COLUMNS].drop_duplicates().reset_index(drop=True)


def load_local_insider_trades(path: str | Path = DEFAULT_LOCAL_PATH) -> tuple[pd.DataFrame, dict[str, str]]:
    candidate = Path(path)
    if not candidate.exists():
        return _empty_frame(), _source_status(
            "Import Anatole",
            "Non activé",
            "Aucun relevé interne n’est chargé.",
        )
    try:
        if candidate.suffix.lower() in {".xlsx", ".xls"}:
            raw = pd.read_excel(candidate)
        else:
            raw = pd.read_csv(candidate)
        frame = _canonicalise_frame(raw, source="Import Anatole")
        return frame, _source_status(
            "Import Anatole",
            "Connecté" if not frame.empty else "Aucune donnée",
            f"{len(frame)} transactions normalisées chargées.",
        )
    except Exception:
        return _empty_frame(), _source_status(
            "Import Anatole",
            "Non disponible",
            "Le relevé interne n’a pas pu être lu correctement.",
        )


# -----------------------------------------------------------------------------
# HTTP et parsing HTML publics sans API
# -----------------------------------------------------------------------------

def _requests_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        }
    )
    return session


def _fetch_html(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    if not url:
        return "", "URL invalide"
    try:
        response = _requests_session().get(url, timeout=timeout)
        if response.status_code >= 400:
            return "", "Accès public limité"
        text = response.text or ""
        if len(text.strip()) < 200:
            return "", "Réponse vide"
        return text, ""
    except requests.Timeout:
        return "", "Délai dépassé"
    except Exception:
        return "", "Non disponible"


def _html_to_lines(html: str) -> list[str]:
    if not html:
        return []
    text = re.sub(r"<script\b[^>]*>.*?</script>", "\n", html, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "\n", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|tr|td|th|li|h1|h2|h3|h4|h5|span|section|article)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def _line_window(lines: list[str], start_tokens: Iterable[str], end_tokens: Iterable[str] = ()) -> list[str]:
    lowered = [line.lower() for line in lines]
    start = 0
    for token in start_tokens:
        token_l = token.lower()
        for i, line in enumerate(lowered):
            if token_l in line:
                start = i + 1
                break
        if start:
            break
    end = len(lines)
    if start:
        for token in end_tokens:
            token_l = token.lower()
            for i in range(start, len(lines)):
                if token_l in lowered[i]:
                    end = i
                    break
            if end != len(lines):
                break
    return lines[start:end]


def _parse_marketbeat_lines(lines: list[str], symbol: str, company: str, url: str) -> pd.DataFrame:
    window = _line_window(
        lines,
        start_tokens=["Transaction Date Insider Buy/Sell", "Insider and Congressional Trades History"],
        end_tokens=["Get Insider Trades Delivered", "Data available from", "Insider Trading Activity - Frequently Asked Questions"],
    )
    if not window:
        window = lines

    rows: list[dict[str, Any]] = []
    date_re = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
    trade_re = re.compile(
        r"\b(?P<kind>Buy|Sell|Purchase|Sale)\b\s+"
        r"(?P<shares>[0-9][0-9,]*)\s+"
        r"(?P<price>(?:C\$|CA\$|\$)?[0-9][0-9,.]*)\s+"
        r"(?P<value>(?:C\$|CA\$|\$)?[0-9][0-9,.]*)",
        flags=re.I,
    )

    i = 0
    while i < len(window):
        line = window[i]
        if not date_re.match(line):
            i += 1
            continue
        trade_date = _as_date(line)
        chunk = []
        j = i + 1
        while j < len(window) and not date_re.match(window[j]):
            chunk.append(window[j])
            j += 1
        joined = " ".join(chunk)
        match = trade_re.search(joined)
        if match:
            before = joined[: match.start()].strip()
            parts = before.split()
            role = ""
            insider = before
            role_tokens = ["Senior Officer", "Director", "Insider", "Officer"]
            for role_candidate in role_tokens:
                idx = before.lower().rfind(role_candidate.lower())
                if idx > 0:
                    insider = before[:idx].strip(" -—")
                    role = before[idx:].strip()
                    break
            kind = match.group("kind")
            shares = _as_float(match.group("shares"))
            price = _as_float(match.group("price"))
            value = _as_float(match.group("value"))
            rows.append(
                {
                    "Date": trade_date,
                    "Ticker": normalise_ticker(symbol),
                    "Symbole Yahoo": to_yahoo_symbol(symbol),
                    "Société": _as_text(company),
                    "Insider": insider,
                    "Rôle": role,
                    "Transaction": kind,
                    "Direction": _direction_from_text(kind),
                    "Actions": shares,
                    "Prix": price,
                    "Valeur": value,
                    "Source": "MarketBeat public",
                    "Lien": url,
                }
            )
        i = j

    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS) if rows else _empty_frame()


def fetch_marketbeat_insider_transactions(
    symbol: str,
    company: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[pd.DataFrame, dict[str, str]]:
    url = marketbeat_insider_url(symbol)
    html, error = _fetch_html(url, timeout=timeout)
    if error:
        return _empty_frame(), _source_status("MarketBeat public", "Couverture limitée", "La source publique n’a pas retourné de données exploitables aujourd’hui.")
    lines = _html_to_lines(html)
    frame = _parse_marketbeat_lines(lines, symbol=symbol, company=company, url=url)
    return frame, _source_status(
        "MarketBeat public",
        "Connecté" if not frame.empty else "Aucune transaction détectée",
        f"{len(frame)} transaction(s) normalisée(s) pour ce titre.",
    )


def _parse_insiderscreener_lines(lines: list[str], symbol: str, company: str, url: str) -> pd.DataFrame:
    window = _line_window(
        lines,
        start_tokens=["##### Trades", "Trades"],
        end_tokens=["##### Explore more", "Explore more", "More insider trading research"],
    )
    if not window:
        window = lines

    rows: list[dict[str, Any]] = []
    current_insider = ""
    current_role = ""
    trade_line_re = re.compile(r"^(?P<kind>Sale|Sell|Purchase|Buy|Planned sale|Planned purchase|Option|Other)\s+(?P<date>\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", re.I)
    value_line_re = re.compile(
        r"Value\s+(?P<value>CA\$|C\$|\$)?(?P<value_num>[0-9][0-9,.]*)\s*\|\s*"
        r"Price\s+(?P<price>[0-9][0-9,.]*)\s*\|\s*"
        r"Shares\s+(?P<shares>[0-9][0-9,]*)",
        re.I,
    )

    i = 0
    while i < len(window):
        line = window[i]
        if re.match(r"^[A-Z][A-Za-zÀ-ÿ'.,\- ]{2,}$", line) and not any(token in line.lower() for token in ["sale", "purchase", "total", "subscription", "transaction", "value", "price", "shares"]):
            # La ligne suivante est souvent le rôle de l'initié.
            nxt = window[i + 1] if i + 1 < len(window) else ""
            if any(token in nxt.lower() for token in ["officer", "director", "issuer", "insider", "board", "executive"]):
                current_insider = line.strip()
                current_role = nxt.strip()
                i += 2
                continue
        trade_match = trade_line_re.match(line)
        if trade_match:
            value_line = ""
            for j in range(i + 1, min(i + 4, len(window))):
                if "Value" in window[j] and "Shares" in window[j]:
                    value_line = window[j]
                    break
            value_match = value_line_re.search(value_line)
            if value_match:
                kind = trade_match.group("kind")
                rows.append(
                    {
                        "Date": _as_date(trade_match.group("date")),
                        "Ticker": normalise_ticker(symbol),
                        "Symbole Yahoo": to_yahoo_symbol(symbol),
                        "Société": _as_text(company),
                        "Insider": current_insider,
                        "Rôle": current_role,
                        "Transaction": kind,
                        "Direction": _direction_from_text(kind),
                        "Actions": _as_float(value_match.group("shares")),
                        "Prix": _as_float(value_match.group("price")),
                        "Valeur": _as_float(value_match.group("value_num")),
                        "Source": "InsiderScreener public",
                        "Lien": url,
                    }
                )
        i += 1

    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS) if rows else _empty_frame()


def fetch_insiderscreener_transactions(
    symbol: str,
    company: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[pd.DataFrame, dict[str, str]]:
    url = insiderscreener_company_url(symbol, company)
    html, error = _fetch_html(url, timeout=timeout)
    if error:
        return _empty_frame(), _source_status("InsiderScreener public", "Couverture limitée", "La source publique n’a pas retourné de données exploitables aujourd’hui.")
    lines = _html_to_lines(html)
    # Évite de normaliser une mauvaise page de recherche comme si elle était l'entreprise.
    if company and not any(_normalise_company_for_slug(company).replace("-", " ").split()[0] in line.lower() for line in lines[:120]):
        return _empty_frame(), _source_status("InsiderScreener public", "À vérifier", "La page publique ne correspond pas clairement au titre sélectionné.")
    frame = _parse_insiderscreener_lines(lines, symbol=symbol, company=company, url=url)
    return frame, _source_status(
        "InsiderScreener public",
        "Connecté" if not frame.empty else "Aucune transaction détectée",
        f"{len(frame)} transaction(s) normalisée(s) pour ce titre.",
    )


# -----------------------------------------------------------------------------
# Sources d’appoint
# -----------------------------------------------------------------------------

def fetch_yahoo_insider_transactions(symbol: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[pd.DataFrame, dict[str, str]]:
    yahoo = to_yahoo_symbol(symbol)
    if not yahoo:
        return _empty_frame(), _source_status("Yahoo Finance public", "Symbole non reconnu", "Le symbole ne peut pas être interrogé automatiquement.")

    urls = [
        f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{quote_plus(yahoo)}?modules=insiderTransactions",
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{quote_plus(yahoo)}?modules=insiderTransactions",
    ]
    session = _requests_session()
    for url in urls:
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code >= 400:
                continue
            payload = response.json()
            result = (payload.get("quoteSummary") or {}).get("result") or []
            data = result[0] if result else {}
            transactions = ((data.get("insiderTransactions") or {}).get("transactions") or [])
            rows: list[dict[str, Any]] = []
            for item in transactions:
                shares = _as_float(item.get("shares"))
                value = _as_float(item.get("value"))
                price = _as_float(item.get("startDatePrice"))
                if math.isnan(price) and not math.isnan(value) and not math.isnan(shares) and shares:
                    price = abs(value / shares)
                transaction = _as_text(item.get("transactionText") or item.get("transaction"))
                rows.append(
                    {
                        "Date": _as_date(item.get("startDate") or item.get("transactionDate")),
                        "Ticker": normalise_ticker(symbol),
                        "Symbole Yahoo": yahoo,
                        "Société": "",
                        "Insider": _as_text(item.get("filerName") or item.get("name")),
                        "Rôle": _as_text(item.get("filerRelation") or item.get("ownership")),
                        "Transaction": transaction,
                        "Direction": _direction_from_text(transaction, shares if not math.isnan(shares) else None),
                        "Actions": shares,
                        "Prix": price,
                        "Valeur": value,
                        "Source": "Yahoo Finance public",
                        "Lien": yahoo_insider_url(symbol),
                    }
                )
            frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS) if rows else _empty_frame()
            return frame, _source_status(
                "Yahoo Finance public",
                "Connecté" if not frame.empty else "Aucune transaction détectée",
                f"{len(frame)} transaction(s) normalisée(s) pour ce titre.",
            )
        except Exception:
            continue

    return _empty_frame(), _source_status("Yahoo Finance public", "Couverture limitée", "Lecture automatique non disponible aujourd’hui.")


def fetch_finnhub_insider_transactions(
    symbol: str,
    days: int = 180,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[pd.DataFrame, dict[str, str]]:
    token = api_key or os.getenv("FINNHUB_API_KEY", "")
    if not token:
        return _empty_frame(), _source_status("Connecteur professionnel", "Non activé", "Connexion fournisseur non activée dans cet environnement.")

    yahoo = to_yahoo_symbol(symbol)
    end = _today()
    start = end - timedelta(days=max(1, int(days or 180)))
    url = "https://finnhub.io/api/v1/stock/insider-transactions"
    params = {"symbol": yahoo, "from": start.isoformat(), "to": end.isoformat(), "token": token}
    try:
        response = _requests_session().get(url, params=params, timeout=timeout)
        if response.status_code >= 400:
            return _empty_frame(), _source_status("Connecteur professionnel", "Non disponible", "Le fournisseur n’a pas retourné de données exploitables.")
        payload = response.json()
        data = payload.get("data", payload if isinstance(payload, list) else [])
        rows: list[dict[str, Any]] = []
        for item in data or []:
            change = _as_float(item.get("change") or item.get("share"))
            shares = abs(change) if not math.isnan(change) else _as_float(item.get("share"))
            price = _as_float(item.get("transactionPrice") or item.get("price"))
            value = abs(shares * price) if not math.isnan(shares) and not math.isnan(price) else math.nan
            code = _as_text(item.get("transactionCode") or item.get("transactionType"))
            rows.append(
                {
                    "Date": _as_date(item.get("transactionDate") or item.get("filingDate")),
                    "Ticker": normalise_ticker(symbol),
                    "Symbole Yahoo": yahoo,
                    "Société": "",
                    "Insider": _as_text(item.get("name")),
                    "Rôle": _as_text(item.get("relationship") or item.get("position")),
                    "Transaction": code,
                    "Direction": _direction_from_text(code, change if not math.isnan(change) else None),
                    "Actions": shares,
                    "Prix": price,
                    "Valeur": value,
                    "Source": "Connecteur professionnel",
                    "Lien": yahoo_insider_url(symbol),
                }
            )
        frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS) if rows else _empty_frame()
        return frame, _source_status(
            "Connecteur professionnel",
            "Connecté" if not frame.empty else "Aucune transaction détectée",
            f"{len(frame)} transaction(s) normalisée(s) pour ce titre.",
        )
    except Exception:
        return _empty_frame(), _source_status("Connecteur professionnel", "Non disponible", "Le fournisseur n’a pas pu être joint correctement.")


# -----------------------------------------------------------------------------
# Consolidation
# -----------------------------------------------------------------------------

def filter_recent(frame: pd.DataFrame, days: int = 180) -> pd.DataFrame:
    if frame is None or frame.empty or "Date" not in frame.columns:
        return _empty_frame()
    result = frame.copy()
    parsed = pd.to_datetime(result["Date"], errors="coerce")
    cutoff = pd.Timestamp(_today() - timedelta(days=max(1, int(days or 180))))
    result = result[parsed.isna() | (parsed >= cutoff)].copy()
    result["_parsed_date"] = pd.to_datetime(result["Date"], errors="coerce")
    result = result.sort_values("_parsed_date", ascending=False, na_position="last").drop(columns=["_parsed_date"])
    return result[CANONICAL_COLUMNS].reset_index(drop=True)


def enrich_with_companies(frame: pd.DataFrame, constituents: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_frame()
    result = frame.copy()
    if constituents is None or constituents.empty or "Ticker" not in constituents.columns:
        return result[CANONICAL_COLUMNS]
    meta = constituents.copy()
    meta["_TickerClean"] = meta["Ticker"].map(normalise_ticker)
    name_map = dict(zip(meta["_TickerClean"], meta.get("Nom", meta["Ticker"])))
    result["Société"] = [
        company if _as_text(company) else _as_text(name_map.get(normalise_ticker(ticker)))
        for company, ticker in zip(result.get("Société", ""), result.get("Ticker", ""))
    ]
    return result[CANONICAL_COLUMNS]


def deduplicate_trades(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_frame()
    result = frame.copy()
    for column in CANONICAL_COLUMNS:
        if column not in result.columns:
            result[column] = "" if column not in {"Actions", "Prix", "Valeur"} else math.nan

    result["_TickerClean"] = result["Ticker"].map(normalise_ticker)
    result["_DateClean"] = result["Date"].astype(str).str[:10].fillna("")
    result["_InsiderClean"] = result["Insider"].astype(str).str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    result["_DirectionClean"] = result["Direction"].astype(str).str.lower().str.strip()
    result["_ActionsClean"] = pd.to_numeric(result["Actions"], errors="coerce").round(0).astype("Int64").astype(str)
    result["_dedup_key"] = result["_DateClean"] + "|" + result["_TickerClean"] + "|" + result["_InsiderClean"] + "|" + result["_DirectionClean"] + "|" + result["_ActionsClean"]

    def first_non_empty(series: pd.Series) -> Any:
        for value in series:
            if _as_text(value):
                return value
        return ""

    grouped = []
    for _, group in result.groupby("_dedup_key", dropna=False, sort=False):
        row = group.iloc[0].copy()
        sources = sorted(set(_as_text(value) for value in group["Source"] if _as_text(value)))
        links = [_as_text(value) for value in group["Lien"] if _as_text(value)]
        row["Source"] = " + ".join(sources) if sources else first_non_empty(group["Source"])
        row["Lien"] = links[0] if links else ""
        for col in ["Société", "Insider", "Rôle", "Transaction"]:
            row[col] = first_non_empty(group[col]) or row.get(col, "")
        grouped.append(row)

    out = pd.DataFrame(grouped)
    return out[CANONICAL_COLUMNS].reset_index(drop=True)


def build_symbol_link_matrix(constituents: pd.DataFrame) -> pd.DataFrame:
    if constituents is None or constituents.empty:
        return pd.DataFrame(columns=["Ticker", "Société", "Secteur", "SEDI", "TMX", "MarketBeat", "InsiderScreener", "Canadian Insider"])
    frame = constituents.copy()
    frame["Ticker"] = frame["Ticker"].map(normalise_ticker)
    company_series = frame.get("Nom", frame["Ticker"])
    out = pd.DataFrame(
        {
            "Ticker": frame["Ticker"],
            "Société": company_series,
            "Secteur": frame.get("Secteur", ""),
            "SEDI": company_series.map(sedi_issuer_search_url),
            "TMX": frame["Ticker"].map(tmx_insider_url),
            "MarketBeat": frame["Ticker"].map(marketbeat_insider_url),
            "InsiderScreener": [insiderscreener_company_url(t, c) for t, c in zip(frame["Ticker"], company_series)],
            "Canadian Insider": frame["Ticker"].map(canadian_insider_url),
        }
    )
    return out.drop_duplicates("Ticker").reset_index(drop=True)


def _company_for_symbol(constituents: pd.DataFrame, symbol: str) -> str:
    if constituents is None or constituents.empty or "Ticker" not in constituents.columns:
        return ""
    clean = normalise_ticker(symbol)
    meta = constituents.copy()
    meta["_TickerClean"] = meta["Ticker"].map(normalise_ticker)
    row = meta[meta["_TickerClean"] == clean].head(1)
    if row.empty:
        return ""
    if "Nom" in row.columns:
        return _as_text(row["Nom"].iloc[0])
    return clean


def collect_insider_trades(
    constituents: pd.DataFrame,
    days: int = 180,
    symbols: Iterable[str] | None = None,
    include_yahoo: bool = False,
    include_finnhub: bool = True,
    include_marketbeat: bool = True,
    include_insiderscreener: bool = True,
    max_public_symbols: int = 12,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe_symbols: list[str] = []
    if constituents is not None and not constituents.empty and "Ticker" in constituents:
        universe_symbols = [normalise_ticker(value) for value in constituents["Ticker"].dropna().tolist()]
    if symbols is not None:
        wanted = [normalise_ticker(value) for value in symbols if normalise_ticker(value)]
    else:
        wanted = universe_symbols
    wanted = list(dict.fromkeys([value for value in wanted if value]))

    frames: list[pd.DataFrame] = []
    sources: list[dict[str, str]] = []

    local, local_status = load_local_insider_trades()
    sources.append(local_status)
    if not local.empty:
        local = local[local["Ticker"].map(normalise_ticker).isin(set(wanted))] if wanted else local
        frames.append(local)

    scan_symbols = wanted[: max(1, int(max_public_symbols or 1))]

    if include_marketbeat and scan_symbols:
        for symbol in scan_symbols:
            company = _company_for_symbol(constituents, symbol)
            frame, status = fetch_marketbeat_insider_transactions(symbol, company=company)
            sources.append(status)
            if not frame.empty:
                frames.append(frame)
    else:
        sources.append(_source_status("MarketBeat public", "Sur demande", "Lecture disponible depuis la vue par titre."))

    if include_insiderscreener and scan_symbols:
        for symbol in scan_symbols:
            company = _company_for_symbol(constituents, symbol)
            frame, status = fetch_insiderscreener_transactions(symbol, company=company)
            sources.append(status)
            if not frame.empty:
                frames.append(frame)
    else:
        sources.append(_source_status("InsiderScreener public", "Sur demande", "Lecture disponible depuis la vue par titre."))

    if include_yahoo and scan_symbols:
        for symbol in scan_symbols:
            frame, status = fetch_yahoo_insider_transactions(symbol)
            sources.append(status)
            if not frame.empty:
                frames.append(frame)
    else:
        sources.append(_source_status("Yahoo Finance public", "Sur demande", "Source complémentaire utilisée au cas par cas."))

    if include_finnhub and wanted:
        token = os.getenv("FINNHUB_API_KEY", "")
        if token:
            for symbol in scan_symbols:
                frame, status = fetch_finnhub_insider_transactions(symbol, days=days, api_key=token)
                sources.append(status)
                if not frame.empty:
                    frames.append(frame)
        else:
            sources.append(_source_status("Connecteur professionnel", "Non activé", "Source optionnelle non nécessaire au mode public."))

    combined = pd.concat(frames, ignore_index=True) if frames else _empty_frame()
    combined = enrich_with_companies(deduplicate_trades(filter_recent(combined, days=days)), constituents)
    return combined, pd.DataFrame(sources, columns=SOURCE_COLUMNS).drop_duplicates().reset_index(drop=True)


def build_insider_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {
            "transactions": 0,
            "companies": 0,
            "buys": 0,
            "sells": 0,
            "net_value": 0.0,
            "buy_ratio": 0.0,
        }
    result = frame.copy()
    values = pd.to_numeric(result.get("Valeur"), errors="coerce").fillna(0.0)
    direction = result.get("Direction", pd.Series(dtype=str)).astype(str)
    buys = int(direction.str.contains("Achat", case=False, na=False).sum())
    sells = int(direction.str.contains("Vente", case=False, na=False).sum())
    signed = values.where(direction.str.contains("Achat", case=False, na=False), -values.where(direction.str.contains("Vente", case=False, na=False), 0.0))
    total_directional = buys + sells
    return {
        "transactions": int(len(result)),
        "companies": int(result.get("Ticker", pd.Series(dtype=str)).nunique()),
        "buys": buys,
        "sells": sells,
        "net_value": float(signed.sum()),
        "buy_ratio": float((buys / total_directional) * 100) if total_directional else 0.0,
    }
