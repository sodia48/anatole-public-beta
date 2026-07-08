from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from core.data import fetch_market_snapshot


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
