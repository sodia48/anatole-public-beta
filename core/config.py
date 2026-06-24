from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

APP_ROOT = Path(__file__).resolve().parents[1]

# En local, les données sont écrites dans ./data.
# Sur un hébergeur avec disque persistant, définis ANATOLE_DATA_DIR.
DATA_DIR = Path(
    os.getenv("ANATOLE_DATA_DIR", str(APP_ROOT / "data"))
).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "dashboard.db"


def _runtime_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value)

    try:
        import streamlit as st

        secret_value = st.secrets.get(name, default)
        if secret_value not in (None, ""):
            return str(secret_value)
    except Exception:
        pass

    return default


DATABASE_URL = _runtime_setting("DATABASE_URL", "").strip()
APP_ENV = _runtime_setting("ANATOLE_ENV", "development").strip().lower()
TORONTO_TZ = ZoneInfo("America/Toronto")

BLACKROCK_HOLDINGS_URL = (
    "https://www.blackrock.com/ca/investors/en/products/239832/"
    "ishares-sptsx-60-index-etf/1464253357814.ajax"
    "?dataType=fund&fileName=XIU_holdings&fileType=csv"
)

EXPECTED_CONSTITUENTS = 60
DEFAULT_PROFILE = "principal"
DEFAULT_WATCHLIST = ["RY.TO", "TD.TO", "SHOP.TO", "ENB.TO"]

# Liste de secours. Les symboles sont au format TSX brut; Yahoo est dérivé dans utils.py.
FALLBACK_TICKERS = [
    "RY", "TD", "SHOP", "ENB", "BMO", "CM", "BNS", "BN", "CNQ", "CP",
    "AEM", "SU", "TRP", "MFC", "CNR", "ABX", "NA", "WPM", "CSU", "ATD",
    "CLS", "SLF", "CCO", "WCN", "FNV", "CVE", "IFC", "DOL", "FFH", "POW",
    "NTR", "FTS", "PPL", "K", "TECK.B", "L", "QSR", "BCE", "FM", "T",
    "IMO", "BIP.UN", "WSP", "BAM", "TOU", "MG", "EMA", "RCI.B", "MRU",
    "H", "GIB.A", "WN", "TRI", "GIL", "CCL.B", "CAE", "SAP", "CTC.A",
    "FSV", "OTEX",
]

FALLBACK_SECTORS = {
    "RY": "Financials", "TD": "Financials", "BMO": "Financials",
    "CM": "Financials", "BNS": "Financials", "BN": "Financials",
    "MFC": "Financials", "NA": "Financials", "SLF": "Financials",
    "IFC": "Financials", "FFH": "Financials", "POW": "Financials",
    "BAM": "Financials",
    "SHOP": "Information Technology", "CSU": "Information Technology",
    "CLS": "Information Technology", "GIB.A": "Information Technology",
    "OTEX": "Information Technology",
    "ENB": "Energy", "CNQ": "Energy", "SU": "Energy", "TRP": "Energy",
    "CVE": "Energy", "PPL": "Energy", "IMO": "Energy", "TOU": "Energy",
    "AEM": "Materials", "ABX": "Materials", "WPM": "Materials",
    "CCO": "Materials", "FNV": "Materials", "NTR": "Materials",
    "K": "Materials", "TECK.B": "Materials", "FM": "Materials",
    "CCL.B": "Materials",
    "CP": "Industrials", "CNR": "Industrials", "WCN": "Industrials",
    "WSP": "Industrials", "BIP.UN": "Industrials", "CAE": "Industrials",
    "TRI": "Industrials", "FSV": "Industrials",
    "ATD": "Consumer Staples", "DOL": "Consumer Staples",
    "L": "Consumer Staples", "MRU": "Consumer Staples",
    "WN": "Consumer Staples", "SAP": "Consumer Staples",
    "QSR": "Consumer Discretionary", "MG": "Consumer Discretionary",
    "GIL": "Consumer Discretionary", "CTC.A": "Consumer Discretionary",
    "FTS": "Utilities", "EMA": "Utilities", "H": "Utilities",
    "BCE": "Communication Services", "T": "Communication Services",
    "RCI.B": "Communication Services",
}

POSITIVE_NEWS_WORDS = {
    "beat", "beats", "growth", "record", "upgrade", "upgraded", "surge",
    "profit", "profits", "strong", "raises", "raised", "buyback", "dividend",
    "acquisition", "expansion", "approval", "partnership", "contract", "wins",
    "outperform", "positive", "rebound", "hausse", "croissance", "record",
    "bénéfice", "relèvement", "dividende", "contrat", "partenariat", "approbation",
}

NEGATIVE_NEWS_WORDS = {
    "miss", "misses", "decline", "downgrade", "downgraded", "fall", "falls",
    "loss", "losses", "weak", "cuts", "cut", "lawsuit", "investigation",
    "warning", "layoff", "layoffs", "recall", "debt", "default", "underperform",
    "negative", "baisse", "recul", "perte", "enquête", "litige", "rappel",
    "licenciement", "dette", "avertissement",
}

NEWS_CATEGORIES = {
    "Résultats financiers": ["earnings", "quarter", "revenue", "eps", "results", "résultats", "trimestre", "bénéfice"],
    "Dividende / rachat": ["dividend", "buyback", "repurchase", "dividende", "rachat"],
    "Acquisition / partenariat": ["acquire", "acquisition", "merger", "deal", "partnership", "acquisition", "fusion", "partenariat"],
    "Analystes": ["upgrade", "downgrade", "target", "rating", "analyst", "objectif", "analyste"],
    "Réglementation / litige": ["regulator", "lawsuit", "investigation", "court", "regulation", "réglementation", "litige", "enquête"],
    "Direction": ["ceo", "cfo", "executive", "appoint", "resign", "direction", "nomme", "démission"],
    "Financement": ["debt", "offering", "financing", "bond", "credit", "dette", "financement", "obligation"],
    "Opérations": ["production", "contract", "launch", "plant", "mine", "capacity", "contrat", "lancement", "usine", "capacité"],
}

ALERT_TYPES = {
    "Prix": "price",
    "Variation quotidienne (%)": "daily_change",
    "RSI 14": "rsi",
    "Volume relatif": "relative_volume",
    "Croisement SMA20/SMA50": "sma_cross",
}

BACKTEST_STRATEGIES = {
    "RSI 30/70": "rsi",
    "Croisement SMA20/SMA50": "sma_cross",
    "Prix au-dessus/sous SMA50": "price_sma50",
    "Bandes de Bollinger": "bollinger",
    "Achat et conservation": "buy_hold",
}
