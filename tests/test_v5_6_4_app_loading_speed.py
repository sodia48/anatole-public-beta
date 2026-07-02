from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_alerts_page_uses_light_bundle_by_default():
    page = (ROOT / "screens" / "4_Alertes.py").read_text(encoding="utf-8")
    assert "load_market_bundle" not in page
    assert "load_light_market_bundle" in page
    assert "show_live_technical = st.toggle" in page
    assert "Chargement technique pour l'évaluation des alertes" in page


def test_diagnostics_page_defers_technical_audit():
    page = (ROOT / "screens" / "10_Diagnostics.py").read_text(encoding="utf-8")
    assert "load_market_bundle" not in page
    assert "load_light_market_bundle" in page
    assert "load_technical_audit = st.toggle" in page
    assert "Historiques techniques" in page
    assert "Non chargé" in page


def test_portfolio_risk_history_is_optional():
    page = (ROOT / "screens" / "3_Portefeuille.py").read_text(encoding="utf-8")
    assert "calculate_risk = st.toggle" in page
    assert "Mise à jour des cotations..." in page
    assert "Chargement des historiques de risque" in page
    assert page.index("calculate_risk = st.toggle") < page.index("fetch_batch_history(history_tickers")


def test_focus_strategy_lab_is_opt_in():
    page = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")
    assert "show_strategy_lab = st.toggle" in page
    assert page.index("if show_strategy_lab:") < page.index("run_strategy_backtest(")
    assert "Laboratoire de stratégies désactivé" in page


def test_shared_data_fetchers_dedupe_and_gate_intraday():
    data = (ROOT / "core" / "data.py").read_text(encoding="utf-8")
    assert "def _use_intraday_snapshot" in data
    assert "ANATOLE_INTRADAY_MAX_TICKERS" in data
    assert "tickers = tuple(dict.fromkeys(tickers))" in data
    assert "tuple(dict.fromkeys(str(ticker) for ticker in tickers" in data
    assert "ANATOLE_FUNDAMENTAL_WORKERS" in data