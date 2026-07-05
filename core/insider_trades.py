from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
DEFAULT_TIMEOUT = 8


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
        text = str(value).replace(",", "").replace("$", "").strip()
        if text in {"", "None", "nan", "NaN"}:
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


def sedi_issuer_search_url(company_or_symbol: str) -> str:
    # SEDI does not provide stable issuer deep links without issuer IDs. The public
    # search page is the safest destination for a symbol/company workflow.
    return "https://www.sedi.ca/sedi/SVTReportsAccessController?locale=en_CA"


def tmx_insider_url(symbol: str) -> str:
    return "https://apps.tmx.com/HttpController?GetPage=SearchInsiderTrade&Language=en"


def yahoo_insider_url(symbol: str) -> str:
    yahoo = to_yahoo_symbol(symbol)
    if not yahoo:
        return ""
    return f"https://ca.finance.yahoo.com/quote/{quote_plus(yahoo)}/insider-transactions/"


def _direction_from_text(text: str, signed_change: float | None = None) -> str:
    if signed_change is not None and not math.isnan(signed_change):
        if signed_change > 0:
            return "Achat"
        if signed_change < 0:
            return "Vente"
    lowered = _as_text(text).lower()
    if any(token in lowered for token in ["buy", "purchase", "acquisition", "achat", "acquired"]):
        return "Achat"
    if any(token in lowered for token in ["sale", "sell", "disposition", "vente", "disposed"]):
        return "Vente"
    if any(token in lowered for token in ["option", "grant", "award", "exercice", "exercise"]):
        return "Options / rémunération"
    return "À classer"


def _canonicalise_frame(frame: pd.DataFrame, source: str = "Fichier local") -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

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
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

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
        return pd.DataFrame(columns=CANONICAL_COLUMNS), {
            "Source": "Import interne",
            "État": "Non activé",
            "Détail": "Aucun relevé d’initiés importé dans Anatole.",
        }
    try:
        if candidate.suffix.lower() in {".xlsx", ".xls"}:
            raw = pd.read_excel(candidate)
        else:
            raw = pd.read_csv(candidate)
        frame = _canonicalise_frame(raw, source="Fichier local")
        return frame, {
            "Source": "Import interne",
            "État": "Connecté" if not frame.empty else "Aucune donnée",
            "Détail": f"{len(frame)} transactions normalisées chargées.",
        }
    except Exception as exc:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), {
            "Source": "Import interne",
            "État": "Non disponible",
            "Détail": "Le relevé importé n’a pas pu être lu correctement.",
        }


def _requests_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
        }
    )
    return session


def fetch_yahoo_insider_transactions(symbol: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[pd.DataFrame, dict[str, str]]:
    yahoo = to_yahoo_symbol(symbol)
    if not yahoo:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), {
            "Source": "Yahoo Finance public",
            "État": "Symbole non reconnu",
            "Détail": "Le symbole sélectionné ne peut pas être interrogé automatiquement.",
        }

    urls = [
        f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{quote_plus(yahoo)}?modules=insiderTransactions",
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{quote_plus(yahoo)}?modules=insiderTransactions",
    ]
    last_error = ""
    session = _requests_session()
    for url in urls:
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code >= 400:
                last_error = f"HTTP {response.status_code}"
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
                if math.isnan(price) and not math.isnan(value) and shares and not math.isnan(shares):
                    price = abs(value / shares) if shares else math.nan
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
            frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
            return frame, {
                "Source": "Yahoo Finance public",
                "État": "Connecté" if not frame.empty else "Aucune transaction détectée",
                "Détail": f"{len(frame)} transaction(s) normalisée(s) pour ce titre.",
            }
        except Exception as exc:
            last_error = exc.__class__.__name__
            continue

    return pd.DataFrame(columns=CANONICAL_COLUMNS), {
        "Source": "Yahoo Finance public",
        "État": "Accès public limité",
        "Détail": "La source publique ne permet pas la lecture automatisée pour ce titre aujourd’hui.",
    }


def fetch_finnhub_insider_transactions(
    symbol: str,
    days: int = 180,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[pd.DataFrame, dict[str, str]]:
    token = api_key or os.getenv("FINNHUB_API_KEY", "")
    if not token:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), {
            "Source": "Finnhub",
            "État": "Source optionnelle inactive",
            "Détail": "Connexion fournisseur non activée dans cet environnement.",
        }

    yahoo = to_yahoo_symbol(symbol)
    end = _today()
    start = end - timedelta(days=max(1, int(days or 180)))
    url = "https://finnhub.io/api/v1/stock/insider-transactions"
    params = {"symbol": yahoo, "from": start.isoformat(), "to": end.isoformat(), "token": token}
    try:
        response = _requests_session().get(url, params=params, timeout=timeout)
        if response.status_code >= 400:
            return pd.DataFrame(columns=CANONICAL_COLUMNS), {
                "Source": "Finnhub",
                "État": "Non disponible",
                "Détail": "Le fournisseur n’a pas retourné de données exploitables.",
            }
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
                    "Source": "Finnhub",
                    "Lien": yahoo_insider_url(symbol),
                }
            )
        frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
        return frame, {
            "Source": "Finnhub",
            "État": "Connecté" if not frame.empty else "Aucune transaction détectée",
            "Détail": f"{len(frame)} transaction(s) normalisée(s) pour ce titre.",
        }
    except Exception as exc:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), {
            "Source": "Finnhub",
            "État": "Non disponible",
            "Détail": "Le fournisseur n’a pas pu être joint correctement.",
        }


def filter_recent(frame: pd.DataFrame, days: int = 180) -> pd.DataFrame:
    if frame is None or frame.empty or "Date" not in frame.columns:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    result = frame.copy()
    parsed = pd.to_datetime(result["Date"], errors="coerce")
    cutoff = pd.Timestamp(_today() - timedelta(days=max(1, int(days or 180))))
    result = result[parsed.isna() | (parsed >= cutoff)].copy()
    result["_parsed_date"] = pd.to_datetime(result["Date"], errors="coerce")
    result = result.sort_values("_parsed_date", ascending=False, na_position="last").drop(columns=["_parsed_date"])
    return result.reset_index(drop=True)


def enrich_with_companies(frame: pd.DataFrame, constituents: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    result = frame.copy()
    if constituents is None or constituents.empty:
        return result[CANONICAL_COLUMNS]
    meta = constituents.copy()
    if "Ticker" not in meta.columns:
        return result[CANONICAL_COLUMNS]
    meta["_TickerClean"] = meta["Ticker"].map(normalise_ticker)
    name_map = dict(zip(meta["_TickerClean"], meta.get("Nom", meta["Ticker"])))
    result["Société"] = [
        company if _as_text(company) else _as_text(name_map.get(normalise_ticker(ticker)))
        for company, ticker in zip(result.get("Société", ""), result.get("Ticker", ""))
    ]
    return result[CANONICAL_COLUMNS]


def deduplicate_trades(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    result = frame.copy()
    for column in CANONICAL_COLUMNS:
        if column not in result.columns:
            result[column] = "" if column not in {"Actions", "Prix", "Valeur"} else math.nan
    key = (
        result["Date"].astype(str).str[:10].fillna("")
        + "|" + result["Ticker"].map(normalise_ticker).fillna("")
        + "|" + result["Insider"].astype(str).str.lower().str.replace(r"\s+", " ", regex=True).fillna("")
        + "|" + result["Direction"].astype(str).str.lower().fillna("")
        + "|" + pd.to_numeric(result["Actions"], errors="coerce").round(0).astype("Int64").astype(str)
    )
    result["_dedup_key"] = key
    result = result.drop_duplicates("_dedup_key", keep="first").drop(columns=["_dedup_key"])
    return result[CANONICAL_COLUMNS].reset_index(drop=True)


def build_symbol_link_matrix(constituents: pd.DataFrame) -> pd.DataFrame:
    if constituents is None or constituents.empty:
        return pd.DataFrame(columns=["Ticker", "Société", "Secteur", "Yahoo", "SEDI", "TMX"])
    frame = constituents.copy()
    frame["Ticker"] = frame["Ticker"].map(normalise_ticker)
    out = pd.DataFrame(
        {
            "Ticker": frame["Ticker"],
            "Société": frame.get("Nom", frame["Ticker"]),
            "Secteur": frame.get("Secteur", ""),
            "Yahoo": frame["Ticker"].map(yahoo_insider_url),
            "SEDI": frame.get("Nom", frame["Ticker"]).map(sedi_issuer_search_url),
            "TMX": frame["Ticker"].map(tmx_insider_url),
        }
    )
    return out.drop_duplicates("Ticker").reset_index(drop=True)


def collect_insider_trades(
    constituents: pd.DataFrame,
    days: int = 180,
    symbols: Iterable[str] | None = None,
    include_yahoo: bool = False,
    include_finnhub: bool = True,
    max_public_symbols: int = 12,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe_symbols = []
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

    if include_finnhub and wanted:
        token = os.getenv("FINNHUB_API_KEY", "")
        if token:
            for symbol in wanted[: max(1, int(max_public_symbols or 1))]:
                frame, status = fetch_finnhub_insider_transactions(symbol, days=days, api_key=token)
                sources.append(status)
                if not frame.empty:
                    frames.append(frame)
        else:
            sources.append({"Source": "Fournisseur optionnel", "État": "Inactif", "Détail": "Connexion fournisseur non activée pour le scan univers."})

    if include_yahoo and wanted:
        for symbol in wanted[: max(1, int(max_public_symbols or 1))]:
            frame, status = fetch_yahoo_insider_transactions(symbol)
            sources.append(status)
            if not frame.empty:
                frames.append(frame)
    else:
        sources.append({"Source": "Source publique", "État": "Sur demande", "Détail": "Lecture ponctuelle disponible depuis la vue par titre."})

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=CANONICAL_COLUMNS)
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
