from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_no_silent_tsx60_fallback():
    runtime = (ROOT / "core" / "runtime.py").read_text(encoding="utf-8")
    assert "Fallback TSX 60" not in runtime
    assert "Univers partiel" in runtime
    assert "clear_universe_caches" in runtime


def test_snapshot_last_good_is_filtered():
    data = (ROOT / "core" / "data.py").read_text(encoding="utf-8")
    assert "def _snapshot_key" in data
    assert "def _last_good_snapshot(tickers" in data
    assert "wanted = set(tickers)" in data


def test_universe_selector_uses_dynamic_keys():
    universe = (ROOT / "core" / "universe.py").read_text(encoding="utf-8")
    assert "market_universe_selector_{current_key}" in universe
    assert "market_universe_inline_{key_suffix}_{current_key}" in universe
    assert "clear_universe_caches" in universe


def test_home_chart_keys_include_universe():
    home = (ROOT / "screens" / "0_Accueil.py").read_text(encoding="utf-8")
    assert "accueil_performance_secteurs_{universe_key}" in home
    assert "minimal_heatmap_{universe_key}" in home
