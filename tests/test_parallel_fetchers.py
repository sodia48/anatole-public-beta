import pandas as pd

import core.data as data
import core.economic_events as economic


def test_news_bundle_collects_all_tickers(monkeypatch):
    monkeypatch.setattr(
        data,
        "_fetch_stock_news_uncached",
        lambda ticker: [
            {
                "Ticker": ticker,
                "Titre": f"News {ticker}",
                "URL": "https://example.com",
                "Source": "Test",
                "Resume": "",
                "Date": "2026-01-01T12:00:00+00:00",
            }
        ],
    )
    data.fetch_news_bundle.clear()

    articles = data.fetch_news_bundle(("RY.TO", "SHOP.TO", "CNQ.TO"))

    assert {item["Ticker"] for item in articles} == {
        "RY.TO",
        "SHOP.TO",
        "CNQ.TO",
    }


def test_economic_sources_are_aggregated(monkeypatch):
    def source(name, country):
        return pd.DataFrame(
            [
                {
                    "Date": "2026-06-20",
                    "Heure": "08:30",
                    "DateTime": pd.Timestamp("2026-06-20 08:30"),
                    "Pays": country,
                    "Devise": "CAD" if country == "Canada" else "USD",
                    "Catégorie": "Inflation",
                    "Événement": name,
                    "Description": "Test",
                    "ImportanceScore": 95,
                    "Importance": "Très élevée",
                    "Source": name,
                    "Lien": "https://example.com",
                }
            ]
        ), ""

    monkeypatch.setattr(
        economic,
        "fetch_statcan_calendar",
        lambda: source("Statistique Canada", "Canada"),
    )
    monkeypatch.setattr(
        economic,
        "fetch_bank_of_canada_calendar",
        lambda: source("Banque du Canada", "Canada"),
    )
    monkeypatch.setattr(
        economic,
        "fetch_bls_calendar",
        lambda start, end: source("BLS", "États-Unis"),
    )
    monkeypatch.setattr(
        economic,
        "fetch_bea_calendar",
        lambda: source("BEA", "États-Unis"),
    )
    monkeypatch.setattr(
        economic,
        "fetch_fomc_calendar",
        lambda start, end: source("Réserve fédérale", "États-Unis"),
    )
    economic.fetch_official_economic_calendar.clear()

    frame, statuses = economic.fetch_official_economic_calendar(
        "2026-06-01",
        "2026-06-30",
    )

    assert len(frame) == 5
    assert set(statuses.values()) == {"OK"}
