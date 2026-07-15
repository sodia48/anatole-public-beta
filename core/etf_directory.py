from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import streamlit as st
import yfinance as yf

from core.data import fetch_market_snapshot
from core.utils import raw_to_yahoo


ETF_COLUMNS = [
    "Ticker",
    "YahooTicker",
    "Nom",
    "Émetteur",
    "Bourse",
    "Devise",
    "Famille",
    "Secteur",
    "Région",
    "Exposition",
    "Coté TSX",
    "Rôle",
    "Source catalogue",
]

# Catalogue intégré volontairement conservateur : il privilégie les FNB faciles à
# vérifier et utiles pour comparer les secteurs du marché canadien.
BASE_ETFS: list[dict[str, object]] = [
    # Canada large marché
    {"Ticker": "XIU", "Nom": "iShares S&P/TSX 60 Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Canada large marché", "Secteur": "Marché canadien", "Région": "Canada", "Exposition": "S&P/TSX 60", "Rôle": "Grandes capitalisations canadiennes"},
    {"Ticker": "XIC", "Nom": "iShares Core S&P/TSX Capped Composite Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Canada large marché", "Secteur": "Marché canadien", "Région": "Canada", "Exposition": "S&P/TSX Composite", "Rôle": "Exposition large au marché canadien"},
    {"Ticker": "ZCN", "Nom": "BMO S&P/TSX Capped Composite Index ETF", "Émetteur": "BMO", "Bourse": "TSX", "Devise": "CAD", "Famille": "Canada large marché", "Secteur": "Marché canadien", "Région": "Canada", "Exposition": "S&P/TSX Composite", "Rôle": "Exposition large au marché canadien"},
    {"Ticker": "VCN", "Nom": "Vanguard FTSE Canada All Cap Index ETF", "Émetteur": "Vanguard", "Bourse": "TSX", "Devise": "CAD", "Famille": "Canada large marché", "Secteur": "Marché canadien", "Région": "Canada", "Exposition": "FTSE Canada All Cap", "Rôle": "Actions canadiennes toutes capitalisations"},
    {"Ticker": "HXT", "Nom": "Global X S&P/TSX 60 Index Corporate Class ETF", "Émetteur": "Global X", "Bourse": "TSX", "Devise": "CAD", "Famille": "Canada large marché", "Secteur": "Marché canadien", "Région": "Canada", "Exposition": "S&P/TSX 60", "Rôle": "Grandes capitalisations canadiennes"},
    {"Ticker": "XMD", "Nom": "iShares S&P/TSX Completion Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Canada complément", "Secteur": "Marché canadien", "Région": "Canada", "Exposition": "S&P/TSX Completion", "Rôle": "Titres hors TSX 60"},
    {"Ticker": "XCS", "Nom": "iShares S&P/TSX SmallCap Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Canada petites capitalisations", "Secteur": "Marché canadien", "Région": "Canada", "Exposition": "S&P/TSX SmallCap", "Rôle": "Petites capitalisations canadiennes"},
    # Canada secteurs GICS / proches
    {"Ticker": "XFN", "Nom": "iShares S&P/TSX Capped Financials Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Finance", "Région": "Canada", "Exposition": "S&P/TSX Capped Financials", "Rôle": "Banques, assureurs et services financiers"},
    {"Ticker": "ZEB", "Nom": "BMO Equal Weight Banks Index ETF", "Émetteur": "BMO", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Finance", "Région": "Canada", "Exposition": "Banques canadiennes équipondérées", "Rôle": "Banques canadiennes"},
    {"Ticker": "XEG", "Nom": "iShares S&P/TSX Capped Energy Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Énergie", "Région": "Canada", "Exposition": "S&P/TSX Capped Energy", "Rôle": "Pétrole, gaz et énergie canadienne"},
    {"Ticker": "ZEO", "Nom": "BMO Equal Weight Oil & Gas Index ETF", "Émetteur": "BMO", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Énergie", "Région": "Canada", "Exposition": "Pétrole et gaz équipondérés", "Rôle": "Producteurs et services énergétiques"},
    {"Ticker": "XMA", "Nom": "iShares S&P/TSX Capped Materials Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Matériaux", "Région": "Canada", "Exposition": "S&P/TSX Capped Materials", "Rôle": "Mines, métaux et matériaux"},
    {"Ticker": "XBM", "Nom": "iShares S&P/TSX Global Base Metals Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Métaux de base", "Région": "Canada / Global", "Exposition": "Métaux de base", "Rôle": "Cuivre, zinc, nickel et producteurs de métaux"},
    {"Ticker": "XGD", "Nom": "iShares S&P/TSX Global Gold Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Or", "Région": "Canada / Global", "Exposition": "Producteurs d'or", "Rôle": "Minières aurifères"},
    {"Ticker": "XIT", "Nom": "iShares S&P/TSX Capped Information Technology Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Technologie", "Région": "Canada", "Exposition": "S&P/TSX Capped Information Technology", "Rôle": "Technologie canadienne"},
    {"Ticker": "XRE", "Nom": "iShares S&P/TSX Capped REIT Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Immobilier", "Région": "Canada", "Exposition": "S&P/TSX Capped REIT", "Rôle": "FPI canadiennes"},
    {"Ticker": "ZRE", "Nom": "BMO Equal Weight REITs Index ETF", "Émetteur": "BMO", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Immobilier", "Région": "Canada", "Exposition": "FPI canadiennes équipondérées", "Rôle": "FPI canadiennes"},
    {"Ticker": "XUT", "Nom": "iShares S&P/TSX Capped Utilities Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Services publics", "Région": "Canada", "Exposition": "S&P/TSX Capped Utilities", "Rôle": "Services publics canadiens"},
    {"Ticker": "ZUT", "Nom": "BMO Equal Weight Utilities Index ETF", "Émetteur": "BMO", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Services publics", "Région": "Canada", "Exposition": "Services publics équipondérés", "Rôle": "Services publics canadiens"},
    {"Ticker": "XST", "Nom": "iShares S&P/TSX Capped Consumer Staples Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur canadien", "Secteur": "Consommation défensive", "Région": "Canada", "Exposition": "S&P/TSX Capped Consumer Staples", "Rôle": "Alimentation, produits essentiels et distribution"},
    # Global / US sectors listed in Canada
    {"Ticker": "XCD", "Nom": "iShares S&P Global Consumer Discretionary Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur mondial coté TSX", "Secteur": "Consommation discrétionnaire", "Région": "Global", "Exposition": "S&P Global 1200 Consumer Discretionary", "Rôle": "Cycle de consommation mondial"},
    {"Ticker": "XHC", "Nom": "iShares Global Healthcare Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur mondial coté TSX", "Secteur": "Santé", "Région": "Global", "Exposition": "S&P Global 1200 Health Care", "Rôle": "Santé mondiale"},
    {"Ticker": "XGI", "Nom": "iShares S&P Global Industrials Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur mondial coté TSX", "Secteur": "Industries", "Région": "Global", "Exposition": "S&P Global 1200 Industrials", "Rôle": "Industries mondiales"},
    {"Ticker": "XUSF", "Nom": "iShares S&P U.S. Financials Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Secteur américain coté TSX", "Secteur": "Finance", "Région": "États-Unis", "Exposition": "S&P U.S. Financials", "Rôle": "Finance américaine"},
    {"Ticker": "XAD", "Nom": "iShares U.S. Aerospace & Defense Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Aérospatiale & défense", "Région": "États-Unis", "Exposition": "Aérospatiale et défense", "Rôle": "Défense, aéronautique et sécurité"},
    {"Ticker": "XCHP", "Nom": "iShares Semiconductor Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Semi-conducteurs", "Région": "États-Unis", "Exposition": "NYSE Semiconductor Index", "Rôle": "Semi-conducteurs"},
    {"Ticker": "XHAK", "Nom": "iShares Cybersecurity and Tech Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Cybersécurité", "Région": "Global", "Exposition": "Cybersécurité et technologies", "Rôle": "Cybersécurité"},
    {"Ticker": "XDNA", "Nom": "iShares Genomics Immunology and Healthcare Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Santé", "Région": "Global", "Exposition": "Génomique, immunologie et santé", "Rôle": "Biotechnologie et santé innovante"},
    {"Ticker": "XCLN", "Nom": "iShares Global Clean Energy Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Énergie propre", "Région": "Global", "Exposition": "Énergie propre", "Rôle": "Transition énergétique"},
    {"Ticker": "XEXP", "Nom": "iShares Exponential Technologies Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Innovation", "Région": "Global", "Exposition": "Technologies exponentielles", "Rôle": "Innovation et technologies disruptives"},
    {"Ticker": "XDRV", "Nom": "iShares Global Electric and Autonomous Vehicles Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Véhicules électriques", "Région": "Global", "Exposition": "Véhicules électriques et autonomes", "Rôle": "Mobilité électrique"},
    {"Ticker": "XETM", "Nom": "iShares S&P/TSX Energy Transition Materials Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Thématique coté TSX", "Secteur": "Matériaux de transition", "Région": "Canada", "Exposition": "Matériaux de transition énergétique", "Rôle": "Métaux et matériaux liés à la transition"},
    # Global / US broad listed on TSX
    {"Ticker": "XUS", "Nom": "iShares Core S&P 500 Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "États-Unis large marché", "Secteur": "Marché américain", "Région": "États-Unis", "Exposition": "S&P 500", "Rôle": "Grandes capitalisations américaines"},
    {"Ticker": "VFV", "Nom": "Vanguard S&P 500 Index ETF", "Émetteur": "Vanguard", "Bourse": "TSX", "Devise": "CAD", "Famille": "États-Unis large marché", "Secteur": "Marché américain", "Région": "États-Unis", "Exposition": "S&P 500", "Rôle": "Grandes capitalisations américaines"},
    {"Ticker": "ZSP", "Nom": "BMO S&P 500 Index ETF", "Émetteur": "BMO", "Bourse": "TSX", "Devise": "CAD", "Famille": "États-Unis large marché", "Secteur": "Marché américain", "Région": "États-Unis", "Exposition": "S&P 500", "Rôle": "Grandes capitalisations américaines"},
    {"Ticker": "XUU", "Nom": "iShares Core S&P U.S. Total Market Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "États-Unis large marché", "Secteur": "Marché américain", "Région": "États-Unis", "Exposition": "Marché américain total", "Rôle": "Actions américaines larges"},
    {"Ticker": "XAW", "Nom": "iShares Core MSCI All Country World ex Canada Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "International", "Secteur": "Marché mondial hors Canada", "Région": "Global hors Canada", "Exposition": "MSCI ACWI ex Canada", "Rôle": "Diversification mondiale hors Canada"},
    {"Ticker": "XEF", "Nom": "iShares Core MSCI EAFE IMI Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "International", "Secteur": "Marchés développés", "Région": "EAFE", "Exposition": "MSCI EAFE IMI", "Rôle": "Europe, Australasie et Extrême-Orient"},
    {"Ticker": "XEC", "Nom": "iShares Core MSCI Emerging Markets IMI Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "International", "Secteur": "Marchés émergents", "Région": "Émergents", "Exposition": "MSCI Emerging Markets IMI", "Rôle": "Actions de marchés émergents"},
    # Income / factors / portfolio tools
    {"Ticker": "XDIV", "Nom": "iShares Core MSCI Canadian Quality Dividend Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Dividendes", "Secteur": "Dividendes canadiens", "Région": "Canada", "Exposition": "Qualité dividendes Canada", "Rôle": "Revenus et qualité"},
    {"Ticker": "XEI", "Nom": "iShares S&P/TSX Composite High Dividend Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Dividendes", "Secteur": "Dividendes canadiens", "Région": "Canada", "Exposition": "Hauts dividendes S&P/TSX", "Rôle": "Revenus canadiens"},
    {"Ticker": "CDZ", "Nom": "iShares S&P/TSX Canadian Dividend Aristocrats Index ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Dividendes", "Secteur": "Dividendes canadiens", "Région": "Canada", "Exposition": "Dividend Aristocrats Canada", "Rôle": "Croissance des dividendes"},
    {"Ticker": "CGL", "Nom": "iShares Gold Bullion ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Commodités", "Secteur": "Or physique", "Région": "Global", "Exposition": "Lingots d'or", "Rôle": "Exposition au prix de l'or"},
    {"Ticker": "SVR", "Nom": "iShares Silver Bullion ETF", "Émetteur": "iShares", "Bourse": "TSX", "Devise": "CAD", "Famille": "Commodités", "Secteur": "Argent physique", "Région": "Global", "Exposition": "Lingots d'argent", "Rôle": "Exposition au prix de l'argent"},
]


SECTOR_MAP: list[dict[str, str]] = [
    {"Secteur": "Finance", "ETF Canada": "XFN, ZEB", "ETF mondial coté TSX": "XUSF", "Lecture": "Banques, assureurs, gestionnaires d'actifs et services financiers."},
    {"Secteur": "Énergie", "ETF Canada": "XEG, ZEO", "ETF mondial coté TSX": "XCLN, XETM", "Lecture": "Pétrole, gaz, énergie propre et matériaux de transition."},
    {"Secteur": "Matériaux", "ETF Canada": "XMA, XBM, XGD", "ETF mondial coté TSX": "XETM", "Lecture": "Métaux, mines, or, matériaux de base et intrants industriels."},
    {"Secteur": "Technologie", "ETF Canada": "XIT", "ETF mondial coté TSX": "XCHP, XHAK, XEXP", "Lecture": "Logiciels, semi-conducteurs, cybersécurité et innovation."},
    {"Secteur": "Immobilier", "ETF Canada": "XRE, ZRE", "ETF mondial coté TSX": "—", "Lecture": "FPI, immobilier commercial, résidentiel, industriel et bureaux."},
    {"Secteur": "Services publics", "ETF Canada": "XUT, ZUT", "ETF mondial coté TSX": "—", "Lecture": "Électricité, gaz, infrastructures réglementées."},
    {"Secteur": "Consommation défensive", "ETF Canada": "XST", "ETF mondial coté TSX": "—", "Lecture": "Alimentation, épicerie, produits essentiels."},
    {"Secteur": "Consommation discrétionnaire", "ETF Canada": "—", "ETF mondial coté TSX": "XCD", "Lecture": "Commerce, luxe, automobile, restauration et dépenses cycliques."},
    {"Secteur": "Santé", "ETF Canada": "—", "ETF mondial coté TSX": "XHC, XDNA", "Lecture": "Santé globale, biotechnologie et innovation médicale."},
    {"Secteur": "Industries", "ETF Canada": "—", "ETF mondial coté TSX": "XGI, XAD", "Lecture": "Transport, défense, équipement, construction et services industriels."},
]


def _prepare_base_frame() -> pd.DataFrame:
    frame = pd.DataFrame(BASE_ETFS)
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame["YahooTicker"] = frame["Ticker"].map(lambda ticker: f"{ticker}.TO")
    frame["Coté TSX"] = frame["Bourse"].astype(str).str.upper().eq("TSX")
    frame["Source catalogue"] = "Catalogue Anatole"
    for column in ETF_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[ETF_COLUMNS].drop_duplicates(subset=["Ticker"]).reset_index(drop=True)


def _load_optional_user_catalogue(path: str | Path = "data/etf_directory.csv") -> pd.DataFrame:
    optional_path = Path(path)
    if not optional_path.exists():
        return pd.DataFrame(columns=ETF_COLUMNS)
    try:
        frame = pd.read_csv(optional_path)
    except Exception:
        return pd.DataFrame(columns=ETF_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=ETF_COLUMNS)
    rename_map = {
        "Symbol": "Ticker",
        "Symbole": "Ticker",
        "Name": "Nom",
        "Issuer": "Émetteur",
        "Exchange": "Bourse",
        "Currency": "Devise",
        "Category": "Famille",
        "Sector": "Secteur",
        "Region": "Région",
        "Exposure": "Exposition",
        "Role": "Rôle",
    }
    frame = frame.rename(columns=rename_map).copy()
    for column in ETF_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame["YahooTicker"] = frame["YahooTicker"].where(
        frame["YahooTicker"].astype(str).str.strip().ne(""),
        frame["Ticker"].map(lambda ticker: f"{ticker}.TO" if ticker else ""),
    )
    frame["Bourse"] = frame["Bourse"].replace("", "TSX")
    frame["Devise"] = frame["Devise"].replace("", "CAD")
    frame["Coté TSX"] = frame["Bourse"].astype(str).str.upper().eq("TSX")
    frame["Source catalogue"] = "Catalogue enrichi"
    return frame[ETF_COLUMNS].dropna(subset=["Ticker"]).drop_duplicates(subset=["Ticker"])


@st.cache_data(ttl=1_800, show_spinner=False)
def load_etf_catalogue() -> pd.DataFrame:
    base = _prepare_base_frame()
    extra = _load_optional_user_catalogue()
    if extra.empty:
        return base
    merged = pd.concat([extra, base], ignore_index=True)
    return merged.drop_duplicates(subset=["Ticker"], keep="first").reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_etf_market_snapshot(tickers: tuple[str, ...]) -> pd.DataFrame:
    tickers = tuple(dict.fromkeys(str(ticker) for ticker in tickers if str(ticker or "").strip()))
    if not tickers:
        return pd.DataFrame()
    try:
        return fetch_market_snapshot(tickers)
    except Exception:
        return pd.DataFrame()


def load_etf_directory(include_prices: bool = True, limit_prices: int = 80) -> pd.DataFrame:
    catalogue = load_etf_catalogue().copy()
    if not include_prices or catalogue.empty:
        return catalogue
    tickers = tuple(catalogue["YahooTicker"].dropna().astype(str).head(limit_prices).tolist())
    snapshot = load_etf_market_snapshot(tickers)
    if snapshot.empty:
        for column in ["Prix", "Variation", "Volume", "SourceCours", "Horodatage"]:
            if column not in catalogue.columns:
                catalogue[column] = pd.NA
        return catalogue
    return catalogue.merge(snapshot, on="YahooTicker", how="left")


def sector_map_frame() -> pd.DataFrame:
    return pd.DataFrame(SECTOR_MAP)


def etf_summary(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {"total": 0, "tsx": 0, "sector": 0, "issuers": 0}
    return {
        "total": int(len(frame)),
        "tsx": int(frame.get("Coté TSX", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
        "sector": int(frame.get("Famille", pd.Series(dtype=str)).astype(str).str.contains("Secteur|Thématique", case=False, regex=True).sum()),
        "issuers": int(frame.get("Émetteur", pd.Series(dtype=str)).nunique()),
    }


# Positions indicatives utilisées seulement si les sources publiques ne retournent pas
# de composition exploitable. Elles servent à donner une lecture pédagogique des
# principaux moteurs, pas à remplacer la fiche officielle du fonds.
FALLBACK_HOLDINGS: list[dict[str, object]] = [
    # Marché canadien large
    {"ETF": "XIU", "Ticker": "RY", "YahooTicker": "RY.TO", "Nom": "Royal Bank of Canada", "Poids": 8.0},
    {"ETF": "XIU", "Ticker": "TD", "YahooTicker": "TD.TO", "Nom": "Toronto-Dominion Bank", "Poids": 6.0},
    {"ETF": "XIU", "Ticker": "SHOP", "YahooTicker": "SHOP.TO", "Nom": "Shopify", "Poids": 5.5},
    {"ETF": "XIU", "Ticker": "ENB", "YahooTicker": "ENB.TO", "Nom": "Enbridge", "Poids": 4.5},
    {"ETF": "XIU", "Ticker": "BN", "YahooTicker": "BN.TO", "Nom": "Brookfield Corporation", "Poids": 4.0},
    {"ETF": "XIC", "Ticker": "RY", "YahooTicker": "RY.TO", "Nom": "Royal Bank of Canada", "Poids": 6.5},
    {"ETF": "XIC", "Ticker": "TD", "YahooTicker": "TD.TO", "Nom": "Toronto-Dominion Bank", "Poids": 5.0},
    {"ETF": "XIC", "Ticker": "SHOP", "YahooTicker": "SHOP.TO", "Nom": "Shopify", "Poids": 4.5},
    {"ETF": "XIC", "Ticker": "ENB", "YahooTicker": "ENB.TO", "Nom": "Enbridge", "Poids": 3.5},
    {"ETF": "XIC", "Ticker": "CNQ", "YahooTicker": "CNQ.TO", "Nom": "Canadian Natural Resources", "Poids": 3.0},
    {"ETF": "ZCN", "Ticker": "RY", "YahooTicker": "RY.TO", "Nom": "Royal Bank of Canada", "Poids": 6.5},
    {"ETF": "ZCN", "Ticker": "TD", "YahooTicker": "TD.TO", "Nom": "Toronto-Dominion Bank", "Poids": 5.0},
    {"ETF": "ZCN", "Ticker": "SHOP", "YahooTicker": "SHOP.TO", "Nom": "Shopify", "Poids": 4.5},
    {"ETF": "VCN", "Ticker": "RY", "YahooTicker": "RY.TO", "Nom": "Royal Bank of Canada", "Poids": 6.0},
    {"ETF": "VCN", "Ticker": "TD", "YahooTicker": "TD.TO", "Nom": "Toronto-Dominion Bank", "Poids": 4.8},
    {"ETF": "VCN", "Ticker": "SHOP", "YahooTicker": "SHOP.TO", "Nom": "Shopify", "Poids": 4.2},
    # Secteurs canadiens
    {"ETF": "XFN", "Ticker": "RY", "YahooTicker": "RY.TO", "Nom": "Royal Bank of Canada", "Poids": 20.0},
    {"ETF": "XFN", "Ticker": "TD", "YahooTicker": "TD.TO", "Nom": "Toronto-Dominion Bank", "Poids": 15.0},
    {"ETF": "XFN", "Ticker": "BMO", "YahooTicker": "BMO.TO", "Nom": "Bank of Montreal", "Poids": 10.0},
    {"ETF": "XFN", "Ticker": "BNS", "YahooTicker": "BNS.TO", "Nom": "Bank of Nova Scotia", "Poids": 9.0},
    {"ETF": "XFN", "Ticker": "MFC", "YahooTicker": "MFC.TO", "Nom": "Manulife Financial", "Poids": 7.0},
    {"ETF": "ZEB", "Ticker": "RY", "YahooTicker": "RY.TO", "Nom": "Royal Bank of Canada", "Poids": 16.7},
    {"ETF": "ZEB", "Ticker": "TD", "YahooTicker": "TD.TO", "Nom": "Toronto-Dominion Bank", "Poids": 16.7},
    {"ETF": "ZEB", "Ticker": "BMO", "YahooTicker": "BMO.TO", "Nom": "Bank of Montreal", "Poids": 16.7},
    {"ETF": "ZEB", "Ticker": "BNS", "YahooTicker": "BNS.TO", "Nom": "Bank of Nova Scotia", "Poids": 16.7},
    {"ETF": "ZEB", "Ticker": "CM", "YahooTicker": "CM.TO", "Nom": "CIBC", "Poids": 16.7},
    {"ETF": "XEG", "Ticker": "CNQ", "YahooTicker": "CNQ.TO", "Nom": "Canadian Natural Resources", "Poids": 25.0},
    {"ETF": "XEG", "Ticker": "SU", "YahooTicker": "SU.TO", "Nom": "Suncor Energy", "Poids": 18.0},
    {"ETF": "XEG", "Ticker": "CVE", "YahooTicker": "CVE.TO", "Nom": "Cenovus Energy", "Poids": 12.0},
    {"ETF": "XEG", "Ticker": "IMO", "YahooTicker": "IMO.TO", "Nom": "Imperial Oil", "Poids": 8.0},
    {"ETF": "XEG", "Ticker": "TOU", "YahooTicker": "TOU.TO", "Nom": "Tourmaline Oil", "Poids": 7.0},
    {"ETF": "XIT", "Ticker": "SHOP", "YahooTicker": "SHOP.TO", "Nom": "Shopify", "Poids": 25.0},
    {"ETF": "XIT", "Ticker": "CSU", "YahooTicker": "CSU.TO", "Nom": "Constellation Software", "Poids": 20.0},
    {"ETF": "XIT", "Ticker": "CLS", "YahooTicker": "CLS.TO", "Nom": "Celestica", "Poids": 10.0},
    {"ETF": "XIT", "Ticker": "GIB.A", "YahooTicker": "GIB-A.TO", "Nom": "CGI", "Poids": 9.0},
    {"ETF": "XIT", "Ticker": "OTEX", "YahooTicker": "OTEX.TO", "Nom": "OpenText", "Poids": 5.0},
    {"ETF": "XMA", "Ticker": "AEM", "YahooTicker": "AEM.TO", "Nom": "Agnico Eagle Mines", "Poids": 18.0},
    {"ETF": "XMA", "Ticker": "ABX", "YahooTicker": "ABX.TO", "Nom": "Barrick Gold", "Poids": 12.0},
    {"ETF": "XMA", "Ticker": "WPM", "YahooTicker": "WPM.TO", "Nom": "Wheaton Precious Metals", "Poids": 10.0},
    {"ETF": "XMA", "Ticker": "NTR", "YahooTicker": "NTR.TO", "Nom": "Nutrien", "Poids": 8.0},
    {"ETF": "XMA", "Ticker": "TECK.B", "YahooTicker": "TECK-B.TO", "Nom": "Teck Resources", "Poids": 7.0},
    {"ETF": "XGD", "Ticker": "AEM", "YahooTicker": "AEM.TO", "Nom": "Agnico Eagle Mines", "Poids": 18.0},
    {"ETF": "XGD", "Ticker": "ABX", "YahooTicker": "ABX.TO", "Nom": "Barrick Gold", "Poids": 12.0},
    {"ETF": "XGD", "Ticker": "FNV", "YahooTicker": "FNV.TO", "Nom": "Franco-Nevada", "Poids": 8.0},
    {"ETF": "XRE", "Ticker": "CAR.UN", "YahooTicker": "CAR-UN.TO", "Nom": "Canadian Apartment Properties REIT", "Poids": 12.0},
    {"ETF": "XRE", "Ticker": "REI.UN", "YahooTicker": "REI-UN.TO", "Nom": "RioCan REIT", "Poids": 9.0},
    {"ETF": "XRE", "Ticker": "GRT.UN", "YahooTicker": "GRT-UN.TO", "Nom": "Granite REIT", "Poids": 8.0},
    {"ETF": "XUT", "Ticker": "FTS", "YahooTicker": "FTS.TO", "Nom": "Fortis", "Poids": 18.0},
    {"ETF": "XUT", "Ticker": "EMA", "YahooTicker": "EMA.TO", "Nom": "Emera", "Poids": 12.0},
    {"ETF": "XUT", "Ticker": "H", "YahooTicker": "H.TO", "Nom": "Hydro One", "Poids": 10.0},
    {"ETF": "XST", "Ticker": "ATD", "YahooTicker": "ATD.TO", "Nom": "Alimentation Couche-Tard", "Poids": 22.0},
    {"ETF": "XST", "Ticker": "L", "YahooTicker": "L.TO", "Nom": "Loblaw", "Poids": 16.0},
    {"ETF": "XST", "Ticker": "DOL", "YahooTicker": "DOL.TO", "Nom": "Dollarama", "Poids": 12.0},
    # États-Unis / thèmes
    {"ETF": "XUS", "Ticker": "NVDA", "YahooTicker": "NVDA", "Nom": "NVIDIA", "Poids": 7.0},
    {"ETF": "XUS", "Ticker": "MSFT", "YahooTicker": "MSFT", "Nom": "Microsoft", "Poids": 6.5},
    {"ETF": "XUS", "Ticker": "AAPL", "YahooTicker": "AAPL", "Nom": "Apple", "Poids": 6.0},
    {"ETF": "XUS", "Ticker": "AMZN", "YahooTicker": "AMZN", "Nom": "Amazon", "Poids": 4.0},
    {"ETF": "XUS", "Ticker": "META", "YahooTicker": "META", "Nom": "Meta Platforms", "Poids": 3.0},
    {"ETF": "VFV", "Ticker": "NVDA", "YahooTicker": "NVDA", "Nom": "NVIDIA", "Poids": 7.0},
    {"ETF": "VFV", "Ticker": "MSFT", "YahooTicker": "MSFT", "Nom": "Microsoft", "Poids": 6.5},
    {"ETF": "VFV", "Ticker": "AAPL", "YahooTicker": "AAPL", "Nom": "Apple", "Poids": 6.0},
    {"ETF": "ZSP", "Ticker": "NVDA", "YahooTicker": "NVDA", "Nom": "NVIDIA", "Poids": 7.0},
    {"ETF": "ZSP", "Ticker": "MSFT", "YahooTicker": "MSFT", "Nom": "Microsoft", "Poids": 6.5},
    {"ETF": "ZSP", "Ticker": "AAPL", "YahooTicker": "AAPL", "Nom": "Apple", "Poids": 6.0},
    {"ETF": "XCHP", "Ticker": "NVDA", "YahooTicker": "NVDA", "Nom": "NVIDIA", "Poids": 12.0},
    {"ETF": "XCHP", "Ticker": "AVGO", "YahooTicker": "AVGO", "Nom": "Broadcom", "Poids": 8.0},
    {"ETF": "XCHP", "Ticker": "AMD", "YahooTicker": "AMD", "Nom": "Advanced Micro Devices", "Poids": 6.0},
    {"ETF": "XCHP", "Ticker": "TSM", "YahooTicker": "TSM", "Nom": "Taiwan Semiconductor", "Poids": 6.0},
    {"ETF": "XHAK", "Ticker": "CRWD", "YahooTicker": "CRWD", "Nom": "CrowdStrike", "Poids": 6.0},
    {"ETF": "XHAK", "Ticker": "PANW", "YahooTicker": "PANW", "Nom": "Palo Alto Networks", "Poids": 6.0},
    {"ETF": "XHAK", "Ticker": "ZS", "YahooTicker": "ZS", "Nom": "Zscaler", "Poids": 4.0},
]


def _normalise_symbol(value: object) -> str:
    return str(value or "").strip().upper().replace("/", ".")


def _normalise_weight(value: object) -> float | None:
    try:
        number = float(str(value).replace("%", "").replace(",", "."))
    except Exception:
        return None
    if pd.isna(number):
        return None
    if 0 < number <= 1:
        return number * 100.0
    return number


def _holding_yahoo_symbol(symbol: str, etf_row: pd.Series | None = None) -> str:
    raw = _normalise_symbol(symbol)
    if not raw:
        return ""
    # Les fonds canadiens sectoriels ont très souvent des composantes TSX.
    region = str(etf_row.get("Région", "") if etf_row is not None else "").lower()
    family = str(etf_row.get("Famille", "") if etf_row is not None else "").lower()
    exposure = str(etf_row.get("Exposition", "") if etf_row is not None else "").lower()
    is_canadian = "canada" in region or "canad" in family or "tsx" in exposure
    if raw.endswith((".TO", ".V")):
        return raw
    if is_canadian:
        return raw_to_yahoo(raw)
    return raw


def _local_holding_candidates(path: str | Path = "data/etf_holdings.csv") -> pd.DataFrame:
    candidate = Path(path)
    if not candidate.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(candidate)
    except Exception:
        return pd.DataFrame()
    if frame.empty:
        return pd.DataFrame()
    rename_map = {
        "Fund": "ETF",
        "FNB": "ETF",
        "Symbol": "Ticker",
        "Symbole": "Ticker",
        "Holding": "Nom",
        "Name": "Nom",
        "Weight": "Poids",
        "Poids (%)": "Poids",
        "Sector": "Secteur",
        "Yahoo": "YahooTicker",
    }
    frame = frame.rename(columns=rename_map).copy()
    for column in ["ETF", "Ticker", "YahooTicker", "Nom", "Poids", "Secteur"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["ETF"] = frame["ETF"].astype(str).str.upper().str.strip()
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame["Poids"] = frame["Poids"].map(_normalise_weight)
    frame["SourcePositions"] = "Catalogue positions"
    return frame[["ETF", "Ticker", "YahooTicker", "Nom", "Poids", "Secteur", "SourcePositions"]]


def _fallback_holdings(etf_ticker: str) -> pd.DataFrame:
    etf = str(etf_ticker or "").upper().strip()
    frame = pd.DataFrame([row for row in FALLBACK_HOLDINGS if str(row.get("ETF", "")).upper() == etf])
    if frame.empty:
        return pd.DataFrame(columns=["ETF", "Ticker", "YahooTicker", "Nom", "Poids", "Secteur", "SourcePositions"])
    frame["Secteur"] = frame.get("Secteur", "")
    frame["SourcePositions"] = "Profil indicatif"
    return frame[["ETF", "Ticker", "YahooTicker", "Nom", "Poids", "Secteur", "SourcePositions"]]


def _holdings_from_yfinance(etf_yahoo_ticker: str, etf_row: pd.Series | None = None) -> pd.DataFrame:
    try:
        ticker = yf.Ticker(str(etf_yahoo_ticker))
        funds_data = getattr(ticker, "funds_data", None)
        raw = getattr(funds_data, "top_holdings", None) if funds_data is not None else None
        if callable(raw):
            raw = raw()
        if raw is None or not isinstance(raw, pd.DataFrame) or raw.empty:
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

    frame = raw.reset_index().copy()
    lower = {str(column).lower().strip(): column for column in frame.columns}
    symbol_col = next((lower[key] for key in lower if key in {"symbol", "ticker", "holding"} or "symbol" in key), None)
    name_col = next((lower[key] for key in lower if key in {"name", "holding name", "company"} or "name" in key), None)
    weight_col = next((lower[key] for key in lower if "weight" in key or "percent" in key or "%" in key), None)
    if symbol_col is None:
        symbol_col = frame.columns[0]
    result = pd.DataFrame()
    result["Ticker"] = frame[symbol_col].map(_normalise_symbol)
    result["Nom"] = frame[name_col].astype(str) if name_col is not None else result["Ticker"]
    result["Poids"] = frame[weight_col].map(_normalise_weight) if weight_col is not None else pd.NA
    result = result.dropna(subset=["Ticker"])
    result = result[result["Ticker"].astype(str).str.len().between(1, 12)]
    if result.empty:
        return pd.DataFrame()
    result["YahooTicker"] = result["Ticker"].map(lambda value: _holding_yahoo_symbol(value, etf_row))
    result["ETF"] = ""
    result["Secteur"] = ""
    result["SourcePositions"] = "Données publiques"
    return result[["ETF", "Ticker", "YahooTicker", "Nom", "Poids", "Secteur", "SourcePositions"]]


@st.cache_data(ttl=900, show_spinner=False)
def load_etf_history(yahoo_ticker: str, period: str = "1y") -> pd.DataFrame:
    ticker = str(yahoo_ticker or "").strip()
    if not ticker:
        return pd.DataFrame()
    try:
        raw = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [str(col[0]) for col in raw.columns]
    close_col = "Close" if "Close" in raw.columns else next((col for col in raw.columns if str(col).lower() == "close"), None)
    if close_col is None:
        return pd.DataFrame()
    frame = raw[[close_col]].rename(columns={close_col: "Prix"}).dropna().copy()
    if frame.empty:
        return pd.DataFrame()
    frame = frame.reset_index()
    date_col = "Date" if "Date" in frame.columns else frame.columns[0]
    frame = frame.rename(columns={date_col: "Date"})
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Prix"] = pd.to_numeric(frame["Prix"], errors="coerce")
    frame = frame.dropna(subset=["Date", "Prix"])
    if frame.empty:
        return pd.DataFrame()
    first = float(frame["Prix"].iloc[0])
    if first and not pd.isna(first):
        frame["Base 100"] = frame["Prix"] / first * 100.0
    else:
        frame["Base 100"] = pd.NA
    frame["Variation journalière"] = frame["Prix"].pct_change() * 100.0
    frame["Rendement"] = (frame["Prix"] / first - 1.0) * 100.0 if first else pd.NA
    frame["Sommet"] = frame["Prix"].cummax()
    frame["Repli depuis sommet"] = (frame["Prix"] / frame["Sommet"] - 1.0) * 100.0
    return frame[["Date", "Prix", "Base 100", "Variation journalière", "Rendement", "Repli depuis sommet"]]


@st.cache_data(ttl=1_800, show_spinner=False)
def load_etf_holdings(etf_ticker: str, etf_yahoo_ticker: str = "") -> pd.DataFrame:
    etf = str(etf_ticker or "").upper().strip()
    if not etf:
        return pd.DataFrame()
    catalogue = load_etf_catalogue()
    etf_row = None
    if not catalogue.empty and "Ticker" in catalogue.columns:
        matched = catalogue[catalogue["Ticker"].astype(str).str.upper().eq(etf)]
        if not matched.empty:
            etf_row = matched.iloc[0]
            if not etf_yahoo_ticker:
                etf_yahoo_ticker = str(etf_row.get("YahooTicker", ""))

    local = _local_holding_candidates()
    if not local.empty:
        filtered = local[local["ETF"].astype(str).str.upper().eq(etf)].copy()
        if not filtered.empty:
            filtered["YahooTicker"] = filtered.apply(
                lambda row: row["YahooTicker"] if str(row.get("YahooTicker", "")).strip() else _holding_yahoo_symbol(row.get("Ticker", ""), etf_row),
                axis=1,
            )
            return filtered.drop_duplicates(subset=["Ticker"], keep="first").reset_index(drop=True)

    public = _holdings_from_yfinance(etf_yahoo_ticker, etf_row) if etf_yahoo_ticker else pd.DataFrame()
    if not public.empty:
        public["ETF"] = etf
        return public.drop_duplicates(subset=["Ticker"], keep="first").reset_index(drop=True)

    fallback = _fallback_holdings(etf)
    return fallback.drop_duplicates(subset=["Ticker"], keep="first").reset_index(drop=True)


@st.cache_data(ttl=900, show_spinner=False)
def load_holding_returns(yahoo_tickers: tuple[str, ...], period: str = "6mo") -> pd.DataFrame:
    tickers = tuple(dict.fromkeys(str(t).strip() for t in yahoo_tickers if str(t or "").strip()))
    if not tickers:
        return pd.DataFrame()
    try:
        raw = yf.download(list(tickers), period=period, interval="1d", auto_adjust=True, progress=False, threads=True)
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()

    if len(tickers) == 1:
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"].iloc[:, 0] if "Close" in raw.columns.get_level_values(0) else pd.Series(dtype=float)
        else:
            close = raw.get("Close", pd.Series(dtype=float))
        series_map = {tickers[0]: close}
    else:
        if isinstance(raw.columns, pd.MultiIndex) and "Close" in raw.columns.get_level_values(0):
            close_df = raw["Close"]
        elif "Close" in raw.columns:
            close_df = raw[["Close"]]
            close_df.columns = [tickers[0]]
        else:
            close_df = pd.DataFrame()
        series_map = {str(col): close_df[col] for col in close_df.columns} if not close_df.empty else {}

    rows = []
    for ticker, series in series_map.items():
        clean = pd.to_numeric(series, errors="coerce").dropna()
        if clean.empty:
            continue
        start = float(clean.iloc[0])
        end = float(clean.iloc[-1])
        if not start:
            continue
        rows.append(
            {
                "YahooTicker": str(ticker),
                "Prix début": start,
                "Prix fin": end,
                "Performance": (end / start - 1.0) * 100.0,
            }
        )
    return pd.DataFrame(rows)


def estimate_etf_contributors(etf_ticker: str, etf_yahoo_ticker: str, period: str = "6mo") -> pd.DataFrame:
    holdings = load_etf_holdings(etf_ticker, etf_yahoo_ticker).copy()
    if holdings.empty:
        return pd.DataFrame()
    holdings["Poids"] = holdings["Poids"].map(_normalise_weight)
    holdings = holdings.dropna(subset=["YahooTicker", "Poids"])
    holdings = holdings[holdings["Poids"].astype(float).gt(0)]
    if holdings.empty:
        return pd.DataFrame()
    returns = load_holding_returns(tuple(holdings["YahooTicker"].astype(str).tolist()), period=period)
    if returns.empty:
        holdings["Performance"] = pd.NA
        holdings["Contribution estimée"] = pd.NA
        return holdings
    merged = holdings.merge(returns, on="YahooTicker", how="left")
    merged["Performance"] = pd.to_numeric(merged["Performance"], errors="coerce")
    merged["Poids"] = pd.to_numeric(merged["Poids"], errors="coerce")
    merged["Contribution estimée"] = merged["Poids"] * merged["Performance"] / 100.0
    merged["Lecture"] = merged["Contribution estimée"].map(
        lambda value: "Moteur positif" if pd.notna(value) and float(value) >= 0 else "Frein"
    )
    return merged.sort_values("Contribution estimée", ascending=False, na_position="last").reset_index(drop=True)


def etf_history_summary(history: pd.DataFrame) -> dict[str, object]:
    if history.empty or "Prix" not in history.columns:
        return {"start": None, "end": None, "return": None, "drawdown": None}
    prices = pd.to_numeric(history["Prix"], errors="coerce").dropna()
    if prices.empty:
        return {"start": None, "end": None, "return": None, "drawdown": None}
    start = float(prices.iloc[0])
    end = float(prices.iloc[-1])
    total = (end / start - 1.0) * 100.0 if start else None
    drawdown_series = pd.to_numeric(history.get("Repli depuis sommet", pd.Series(dtype=float)), errors="coerce").dropna()
    drawdown = float(drawdown_series.min()) if not drawdown_series.empty else None
    return {"start": start, "end": end, "return": total, "drawdown": drawdown}


@st.cache_data(ttl=90, show_spinner=False)
def load_etf_quote(etf_ticker: str, etf_yahoo_ticker: str = "") -> dict[str, object]:
    """Return the most recent available quote for an ETF.

    The data source can be live or delayed depending on the market-data provider.
    The function is defensive: if one path fails, it falls back to recent daily data
    so the ETF page remains usable on Render.
    """
    etf = str(etf_ticker or "").upper().strip()
    yahoo = str(etf_yahoo_ticker or "").strip()
    if not yahoo and etf:
        catalogue = load_etf_catalogue()
        if not catalogue.empty and "Ticker" in catalogue.columns:
            match = catalogue[catalogue["Ticker"].astype(str).str.upper().eq(etf)]
            if not match.empty:
                yahoo = str(match.iloc[0].get("YahooTicker", ""))
    if not yahoo and etf:
        yahoo = raw_to_yahoo(etf)
    result: dict[str, object] = {
        "Ticker": etf,
        "YahooTicker": yahoo,
        "Prix": None,
        "Variation": None,
        "VariationPct": None,
        "Volume": None,
        "Devise": None,
        "Ouverture": None,
        "HautJour": None,
        "BasJour": None,
        "ClôturePrécédente": None,
        "Haut52S": None,
        "Bas52S": None,
        "SourceCours": "Indisponible",
    }
    if not yahoo:
        return result

    try:
        ticker = yf.Ticker(yahoo)
        fast = getattr(ticker, "fast_info", None)
        if fast is not None:
            def _fast_get(*names: str):
                for name in names:
                    try:
                        value = fast.get(name) if hasattr(fast, "get") else getattr(fast, name)
                    except Exception:
                        value = None
                    if value is not None:
                        return value
                return None

            price = _fast_get("last_price", "lastPrice", "regular_market_price")
            previous = _fast_get("previous_close", "previousClose", "regular_market_previous_close")
            result.update(
                {
                    "Prix": price,
                    "Volume": _fast_get("last_volume", "lastVolume", "volume"),
                    "Devise": _fast_get("currency"),
                    "Ouverture": _fast_get("open", "regular_market_open"),
                    "HautJour": _fast_get("day_high", "dayHigh"),
                    "BasJour": _fast_get("day_low", "dayLow"),
                    "ClôturePrécédente": previous,
                    "Haut52S": _fast_get("year_high", "yearHigh"),
                    "Bas52S": _fast_get("year_low", "yearLow"),
                    "SourceCours": "Marché disponible",
                }
            )
            try:
                if price is not None and previous not in (None, 0):
                    result["Variation"] = float(price) - float(previous)
                    result["VariationPct"] = (float(price) / float(previous) - 1.0) * 100.0
            except Exception:
                pass
            if result.get("Prix") is not None:
                return result
    except Exception:
        pass

    try:
        raw = yf.download(yahoo, period="7d", interval="1d", auto_adjust=False, progress=False, threads=False)
    except Exception:
        raw = pd.DataFrame()
    if raw is None or raw.empty:
        return result
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [str(col[0]) for col in raw.columns]
    price_col = "Close" if "Close" in raw.columns else next((col for col in raw.columns if str(col).lower() == "close"), None)
    volume_col = "Volume" if "Volume" in raw.columns else next((col for col in raw.columns if str(col).lower() == "volume"), None)
    high_col = "High" if "High" in raw.columns else next((col for col in raw.columns if str(col).lower() == "high"), None)
    low_col = "Low" if "Low" in raw.columns else next((col for col in raw.columns if str(col).lower() == "low"), None)
    open_col = "Open" if "Open" in raw.columns else next((col for col in raw.columns if str(col).lower() == "open"), None)
    if price_col is None:
        return result
    clean = raw.dropna(subset=[price_col]).copy()
    if clean.empty:
        return result
    last = clean.iloc[-1]
    prev = clean.iloc[-2] if len(clean) > 1 else None
    price = float(last[price_col])
    previous = float(prev[price_col]) if prev is not None else None
    result.update(
        {
            "Prix": price,
            "Volume": float(last[volume_col]) if volume_col and pd.notna(last.get(volume_col)) else None,
            "Ouverture": float(last[open_col]) if open_col and pd.notna(last.get(open_col)) else None,
            "HautJour": float(last[high_col]) if high_col and pd.notna(last.get(high_col)) else None,
            "BasJour": float(last[low_col]) if low_col and pd.notna(last.get(low_col)) else None,
            "ClôturePrécédente": previous,
            "SourceCours": "Marché disponible",
        }
    )
    if previous not in (None, 0):
        result["Variation"] = price - previous
        result["VariationPct"] = (price / previous - 1.0) * 100.0
    return result


def etf_detail_sources(etf_ticker: str, etf_yahoo_ticker: str = "") -> dict[str, str]:
    """Useful public links for an ETF detail card."""
    etf = str(etf_ticker or "").upper().strip()
    yahoo = str(etf_yahoo_ticker or "").strip() or raw_to_yahoo(etf)
    return {
        "Yahoo Finance": f"https://finance.yahoo.com/quote/{yahoo}",
        "TMX Money": f"https://money.tmx.com/en/quote/{etf}",
    }
