from __future__ import annotations

import importlib
import tempfile

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest


def test_all_registered_pages_render_without_exception(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ANATOLE_DATA_DIR", tmp)
        monkeypatch.setenv("ANATOLE_PUBLIC_BETA", "false")
        monkeypatch.delenv("DATABASE_URL", raising=False)

        import core.config
        import core.database
        import core.data
        import core.economic_events
        import core.pro_chart
        import core.public_beta
        import core.runtime

        importlib.reload(core.config)
        importlib.reload(core.database)
        importlib.reload(core.public_beta)

        tickers = [
            "RY.TO",
            "TD.TO",
            "SHOP.TO",
            "CNQ.TO",
            "ABX.TO",
            "CNR.TO",
        ]
        raw = ["RY", "TD", "SHOP", "CNQ", "ABX", "CNR"]
        sectors = [
            "Financials",
            "Financials",
            "Information Technology",
            "Energy",
            "Materials",
            "Industrials",
        ]
        constituents = pd.DataFrame(
            {
                "Ticker": raw,
                "Nom": [
                    "Royal Bank",
                    "TD Bank",
                    "Shopify",
                    "Canadian Natural",
                    "Barrick Gold",
                    "Canadian National",
                ],
                "Secteur": sectors,
                "PoidsIndice": [12, 10, 9, 8, 6, 5],
                "YahooTicker": tickers,
                "SourceComposition": "test",
            }
        )
        market = constituents.copy()
        market["Prix"] = [205, 110, 150, 52, 30, 165]
        market["CloturePrecedente"] = [203, 111, 147, 53, 29, 164]
        market["Variation"] = (
            market["Prix"] / market["CloturePrecedente"] - 1
        ) * 100
        market["PlusHaut"] = market["Prix"] * 1.01
        market["PlusBas"] = market["Prix"] * 0.99
        market["Volume"] = [1e6, 8e5, 2e6, 7e5, 9e5, 6e5]
        market["SourceCours"] = "test"
        market["Horodatage"] = pd.Timestamp.now()

        index = pd.date_range("2025-01-01", periods=300, freq="B")
        rng = np.random.default_rng(4)
        histories: dict[str, pd.DataFrame] = {}
        for number, ticker in enumerate(tickers + ["XIU.TO"]):
            close = 80 + number * 10 + np.cumsum(
                rng.normal(0.05, 1, len(index))
            )
            histories[ticker] = pd.DataFrame(
                {
                    "Open": close + rng.normal(0, 0.2, len(index)),
                    "High": close + 1,
                    "Low": close - 1,
                    "Close": close,
                    "Volume": rng.integers(100_000, 2_000_000, len(index)),
                },
                index=index,
            )

        from core.analytics import build_feature_table

        snapshot_columns = [
            "YahooTicker",
            "Prix",
            "CloturePrecedente",
            "Variation",
            "PlusHaut",
            "PlusBas",
            "Volume",
            "SourceCours",
            "Horodatage",
        ]
        features = build_feature_table(
            constituents,
            histories,
            market[snapshot_columns].copy(),
        )
        diagnostics = {
            "actual": 60,
            "expected": 60,
            "status": "OK",
            "source": "test",
            "error": "",
            "duplicates": [],
            "missing_vs_fallback": [],
            "new_vs_fallback": [],
        }

        def load_constituents():
            return constituents.copy(), diagnostics.copy()

        def fetch_snapshot(requested):
            return market[market["YahooTicker"].isin(requested)].copy()

        def fetch_batch(requested, period="1y", interval="1d"):
            return {
                ticker: histories.get(ticker, pd.DataFrame()).copy()
                for ticker in requested
            }

        def fetch_history(ticker, period="1y", interval="1d"):
            return histories.get(ticker, histories[tickers[0]]).copy()

        def company_info(ticker):
            row = market.loc[market["YahooTicker"] == ticker].iloc[0]
            return {
                "longName": row["Nom"],
                "shortName": row["Nom"],
                "sector": row["Secteur"],
                "industry": "Diversified",
                "currency": "CAD",
                "marketCap": 1e11,
                "enterpriseValue": 1.1e11,
                "trailingPE": 15.2,
                "forwardPE": 14.1,
                "priceToBook": 2.3,
                "dividendYield": 0.035,
                "profitMargins": 0.18,
                "revenueGrowth": 0.07,
                "earningsGrowth": 0.05,
                "returnOnEquity": 0.16,
                "returnOnAssets": 0.06,
                "debtToEquity": 80,
                "currentRatio": 1.2,
                "targetMeanPrice": row["Prix"] * 1.1,
                "numberOfAnalystOpinions": 12,
                "recommendationKey": "buy",
                "recommendationMean": 2.1,
                "fiftyTwoWeekHigh": row["Prix"] * 1.2,
                "fiftyTwoWeekLow": row["Prix"] * 0.7,
                "longBusinessSummary": "Entreprise de test.",
            }

        def fundamentals(requested):
            return pd.DataFrame(
                [
                    {
                        "YahooTicker": ticker,
                        "MarketCap": 1e11,
                        "PE": 15,
                        "ForwardPE": 14,
                        "DividendYield": 3.5,
                        "Beta": 1.0,
                        "ProfitMargin": 18,
                        "RevenueGrowth": 7,
                        "DebtToEquity": 80,
                        "TargetMeanPrice": 200,
                        "Currency": "CAD",
                    }
                    for ticker in requested
                ]
            )

        def news_bundle(requested):
            return [
                {
                    "Ticker": ticker,
                    "Titre": f"{ticker} reports strong results",
                    "URL": "https://example.com",
                    "Source": "Test",
                    "Resume": "Growth and profit improve",
                    "Date": pd.Timestamp.now(tz="UTC").isoformat(),
                }
                for ticker in requested
            ]

        def company_financials(ticker):
            metrics = {
                key: {"value": value, "period": "2025", "source": "test"}
                for key, value in {
                    "revenue": 1e10,
                    "net_income": 2e9,
                    "free_cashflow": 1.5e9,
                    "debt": 5e9,
                    "cash": 2e9,
                    "profit_margin": 0.2,
                    "current_ratio": 1.2,
                    "revenue_growth": 0.08,
                    "earnings_growth": 0.06,
                    "return_on_equity": 0.15,
                    "return_on_assets": 0.07,
                    "equity": 1e10,
                }.items()
            }
            table = pd.DataFrame(
                {"Indicateur": ["Revenue"], "2025": ["10.00 G"]}
            )
            return {
                "info": company_info(ticker),
                "metrics": metrics,
                "income": table,
                "balance": table,
                "cashflow": table,
                "source": "test",
            }

        patches = {
            "load_constituents": load_constituents,
            "fetch_market_snapshot": fetch_snapshot,
            "fetch_batch_history": fetch_batch,
            "fetch_history": fetch_history,
            "fetch_company_info": company_info,
            "fetch_fundamentals": fundamentals,
            "fetch_news_bundle": news_bundle,
            "fetch_stock_news": lambda ticker: news_bundle((ticker,)),
            "fetch_calendar_bundles": lambda requested: {
                ticker: {
                    "ticker": ticker,
                    "calendar": {},
                    "earnings": [],
                    "dividends": [],
                    "splits": [],
                    "key_dates": [],
                }
                for ticker in requested
            },
            "fetch_dividend_history": lambda ticker, period="10y": (
                pd.DataFrame(
                    {
                        "Date": pd.date_range(
                            "2024-01-01", periods=4, freq="QE"
                        ),
                        "Dividende": [1, 1, 1.1, 1.1],
                    }
                )
            ),
            "fetch_company_financials": company_financials,
            "fetch_analyst_consensus": lambda ticker: {
                "metrics": {
                    "recommendation": "Achat",
                    "recommendation_mean": 2.1,
                    "analyst_count": 10,
                    "current_price": 100,
                    "target_low": 90,
                    "target_high": 130,
                    "target_mean": 115,
                    "target_median": 112,
                    "upside_mean": 0.15,
                },
                "summary": pd.DataFrame(
                    {"Période": ["0m"], "Achat": [8], "Conserver": [2]}
                ),
                "upgrades": pd.DataFrame(),
                "source": "test",
            },
            "fetch_insider_activity": lambda ticker: {
                "transactions": pd.DataFrame(
                    {
                        "Date": ["2026-01-01"],
                        "Initié": ["A"],
                        "Transaction": ["Achat"],
                        "Actions": [100],
                    }
                ),
                "purchases": pd.DataFrame(),
                "roster": pd.DataFrame(),
                "ownership": {
                    "held_percent_insiders": 0.02,
                    "held_percent_institutions": 0.7,
                    "shares_outstanding": 1e9,
                    "float_shares": 9e8,
                },
                "source": "test",
                "official_url": "https://example.com",
            },
        }
        for name, function in patches.items():
            monkeypatch.setattr(core.data, name, function)

        monkeypatch.setattr(
            core.runtime,
            "load_light_market_bundle",
            lambda: (
                constituents.copy(),
                diagnostics.copy(),
                market.copy(),
            ),
        )
        monkeypatch.setattr(
            core.runtime,
            "load_technical_bundle",
            lambda: (
                constituents.copy(),
                diagnostics.copy(),
                market.copy(),
                features.copy(),
            ),
        )
        monkeypatch.setattr(
            core.runtime,
            "load_market_bundle",
            core.runtime.load_technical_bundle,
        )
        monkeypatch.setattr(
            core.economic_events,
            "fetch_official_economic_calendar",
            lambda *args, **kwargs: (
                pd.DataFrame(
                    [
                        {
                            "Date": "2026-06-20",
                            "Heure": "08:30",
                            "DateTime": pd.Timestamp("2026-06-20 08:30"),
                            "Pays": "Canada",
                            "Devise": "CAD",
                            "Catégorie": "Inflation",
                            "Événement": "IPC",
                            "Description": "Test",
                            "ImportanceScore": 95,
                            "Importance": "Très élevée",
                            "Source": "Statistique Canada",
                            "Lien": "https://example.com",
                        }
                    ]
                ),
                {"Statistique Canada": "OK"},
            ),
        )
        monkeypatch.setattr(
            core.pro_chart,
            "render_professional_chart",
            lambda *args, **kwargs: None,
        )

        context = core.public_beta.BetaContext(
            profile="principal",
            display_name="Admin",
            email="admin@example.com",
            authenticated=True,
            is_admin=True,
            access_mode="login",
            public_beta=False,
        )
        monkeypatch.setattr(
            core.public_beta,
            "bootstrap_public_beta",
            lambda: context,
        )
        monkeypatch.setattr(
            core.public_beta,
            "current_context",
            lambda: context,
        )

        core.database.init_db(force=True)
        profile = core.database.ensure_profile("principal")
        core.database.replace_positions(
            profile,
            pd.DataFrame(
                [
                    {
                        "ticker": "RY.TO",
                        "quantity": 10,
                        "average_cost": 180,
                        "notes": "test",
                    },
                    {
                        "ticker": "SHOP.TO",
                        "quantity": 5,
                        "average_cost": 120,
                        "notes": "",
                    },
                ]
            ),
        )

        pages = [
            "screens/0_Accueil.py",
            "screens/1_Screener.py",
            "screens/2_Comparateur.py",
            "screens/3_Portefeuille.py",
            "screens/4_Alertes.py",
            "screens/5_Actualites.py",
            "screens/6_Calendrier.py",
            "screens/7_Backtesting.py",
            "screens/8_Correlations.py",
            "screens/9_Watchlist.py",
            "screens/10_Diagnostics.py",
            "screens/11_Workspaces.py",
            "screens/12_Reports.py",
            "screens/13_Assistant.py",
            "screens/14_Focus.py",
            "screens/15_Market_Drivers.py",
            "screens/16_Notifications.py",
            "screens/17_Preferences.py",
            "screens/18_Feedback.py",
            "screens/19_Confidentialite.py",
            "screens/20_Conditions.py",
            "screens/21_Beta_Status.py",
        ]

        app = AppTest.from_file("app.py", default_timeout=30)
        app.run()
        assert not app.exception

        for page in pages:
            app.switch_page(page).run(timeout=30)
            assert not app.exception, (
                page,
                [exception.message for exception in app.exception],
            )
