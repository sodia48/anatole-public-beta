
from core.fundamental_fallback import (
    _normalise_payload,
    merge_tradingview_into_info,
    yahoo_to_tradingview,
    TRADINGVIEW_FIELDS,
)


def test_tradingview_symbol_mapping():
    assert yahoo_to_tradingview("SHOP.TO") == "TSX:SHOP"
    assert yahoo_to_tradingview("TECK-B.TO") == "TSX:TECK.B"
    assert yahoo_to_tradingview("BIP-UN.TO") == "TSX:BIP.UN"


def test_tradingview_payload_and_merge():
    values = [None] * len(TRADINGVIEW_FIELDS)
    data = dict(zip(TRADINGVIEW_FIELDS, values))
    data.update({
        "industry": "Internet Software/Services",
        "market_cap_basic": 100_000_000,
        "price_earnings_ttm": 25,
        "total_revenue_yoy_growth_ttm": 12.5,
        "return_on_equity": 18.0,
    })
    payload = {"data": [{"s": "TSX:SHOP", "d": [data[k] for k in TRADINGVIEW_FIELDS]}]}
    parsed = _normalise_payload(payload)
    assert parsed["market_cap_basic"] == 100_000_000
    assert parsed["total_revenue_yoy_growth_ttm"] == 0.125
    assert parsed["return_on_equity"] == 0.18
    merged = merge_tradingview_into_info({}, parsed)
    assert merged["industry"] == "Internet Software/Services"
    assert merged["marketCap"] == 100_000_000
    assert merged["trailingPE"] == 25
