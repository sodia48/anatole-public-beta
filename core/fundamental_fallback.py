from __future__ import annotations

from typing import Any

import numpy as np
import requests
import streamlit as st

from core.utils import safe_float, yahoo_to_raw


TRADINGVIEW_SCANNER_URL = "https://scanner.tradingview.com/canada/scan"

TRADINGVIEW_FIELDS = [
    "name",
    "description",
    "sector",
    "industry",
    "currency",
    "fundamental_currency_code",
    "close",
    "market_cap_basic",
    "enterprise_value_fq",
    "price_earnings_ttm",
    "price_earnings_forward_fy",
    "price_book_fq",
    "total_revenue_ttm",
    "net_income_ttm",
    "free_cash_flow_ttm",
    "total_debt_fq",
    "total_assets_fq",
    "total_equity_fq",
    "cash_n_short_term_invest_fq",
    "total_current_assets_fq",
    "total_current_liabilities_fq",
    "current_ratio",
    "quick_ratio_fq",
    "debt_to_equity",
    "return_on_equity",
    "return_on_assets",
    "gross_margin",
    "operating_margin",
    "net_margin_ttm",
    "total_revenue_yoy_growth_ttm",
    "net_income_yoy_growth_ttm",
    "earnings_per_share_diluted_yoy_growth_ttm",
    "earnings_per_share_diluted_ttm",
    "price_52_week_high",
    "price_52_week_low",
    "total_shares_outstanding_current",
    "number_of_employees",
    "price_target_average",
    "price_target_high",
    "price_target_low",
    "price_target_median",
    "recommendation_buy",
    "recommendation_hold",
    "recommendation_sell",
    "recommendation_total",
]

PERCENT_FIELDS = {
    "return_on_equity",
    "return_on_assets",
    "gross_margin",
    "operating_margin",
    "net_margin_ttm",
    "total_revenue_yoy_growth_ttm",
    "net_income_yoy_growth_ttm",
    "earnings_per_share_diluted_yoy_growth_ttm",
}


def yahoo_to_tradingview(ticker: str) -> str:
    raw = yahoo_to_raw(ticker).replace("-", ".")
    return f"TSX:{raw}"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (compatible; Anatole/4.7.0)",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
        "Content-Type": "application/json",
    }


def _normalise_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not rows:
        return {}
    values = rows[0].get("d", [])
    if not isinstance(values, list):
        return {}
    result = dict(zip(TRADINGVIEW_FIELDS, values))
    for field in PERCENT_FIELDS:
        number = safe_float(result.get(field))
        result[field] = number / 100 if not np.isnan(number) else np.nan
    return result


@st.cache_data(ttl=21_600, show_spinner=False)
def fetch_tradingview_fundamentals(ticker: str) -> dict[str, Any]:
    symbol = yahoo_to_tradingview(ticker)
    payload = {
        "symbols": {"tickers": [symbol], "query": {"types": []}},
        "options": {"lang": "fr"},
        "columns": TRADINGVIEW_FIELDS,
        "range": [0, 1],
    }
    try:
        response = requests.post(
            TRADINGVIEW_SCANNER_URL,
            json=payload,
            headers=_headers(),
            timeout=12,
        )
        response.raise_for_status()
        result = _normalise_payload(response.json())
        if result:
            result["symbol"] = symbol
            result["source"] = "TradingView Screener"
        return result
    except Exception:
        return {}


def merge_tradingview_into_info(info: dict[str, Any], tv: dict[str, Any]) -> dict[str, Any]:
    merged = dict(info or {})
    mapping = {
        "description": "longName",
        "sector": "sector",
        "industry": "industry",
        "currency": "currency",
        "fundamental_currency_code": "financialCurrency",
        "close": "currentPrice",
        "market_cap_basic": "marketCap",
        "enterprise_value_fq": "enterpriseValue",
        "price_earnings_ttm": "trailingPE",
        "price_earnings_forward_fy": "forwardPE",
        "price_book_fq": "priceToBook",
        "total_revenue_ttm": "totalRevenue",
        "net_income_ttm": "netIncomeToCommon",
        "free_cash_flow_ttm": "freeCashflow",
        "ebitda": "ebitda",
        "total_debt_fq": "totalDebt",
        "total_assets_fq": "totalAssets",
        "total_equity_fq": "totalStockholderEquity",
        "cash_n_short_term_invest_fq": "totalCash",
        "total_current_assets_fq": "totalCurrentAssets",
        "total_current_liabilities_fq": "totalCurrentLiabilities",
        "current_ratio": "currentRatio",
        "quick_ratio_fq": "quickRatio",
        "debt_to_equity": "debtToEquity",
        "return_on_equity": "returnOnEquity",
        "return_on_assets": "returnOnAssets",
        "gross_margin": "grossMargins",
        "operating_margin": "operatingMargins",
        "net_margin_ttm": "profitMargins",
        "total_revenue_yoy_growth_ttm": "revenueGrowth",
        "net_income_yoy_growth_ttm": "earningsGrowth",
        "earnings_per_share_diluted_ttm": "trailingEps",
        "price_52_week_high": "fiftyTwoWeekHigh",
        "price_52_week_low": "fiftyTwoWeekLow",
        "total_shares_outstanding_current": "sharesOutstanding",
        "number_of_employees": "fullTimeEmployees",
        "price_target_average": "targetMeanPrice",
        "price_target_high": "targetHighPrice",
        "price_target_low": "targetLowPrice",
        "price_target_median": "targetMedianPrice",
        "recommendation_total": "numberOfAnalystOpinions",
    }
    for source_key, target_key in mapping.items():
        candidate = tv.get(source_key)
        current = merged.get(target_key)
        missing = current in (None, "") or (isinstance(current, float) and np.isnan(current))
        if missing and candidate not in (None, ""):
            merged[target_key] = candidate
    if not merged.get("shortName") and tv.get("name"):
        merged["shortName"] = tv["name"]
    return merged
