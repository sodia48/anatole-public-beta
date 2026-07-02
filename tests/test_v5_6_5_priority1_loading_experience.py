from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fast_snapshot_cache_mode_exists():
    data = (ROOT / "core" / "data.py").read_text(encoding="utf-8")
    assert "ANATOLE_FAST_START" in data
    assert "ANATOLE_FAST_REFRESH_SECONDS" in data
    assert "def _fast_cached_snapshot" in data
    assert "def _refresh_snapshot_background" in data
    assert "def _download_market_snapshot" in data
    assert "StatutDonnee" in data
    assert "Cache rapide Anatole" in data


def test_data_quality_shows_status():
    quality = (ROOT / "core" / "data_quality.py").read_text(encoding="utf-8")
    runtime = (ROOT / "core" / "runtime.py").read_text(encoding="utf-8")
    assert "def status_summary" in quality
    assert 'diagnostics.get("data_status") or status_summary(frame)' in quality
    assert "Statut :" in quality
    assert "def _market_data_status" in runtime
    assert 'diagnostics["data_status"] = _market_data_status(market)' in runtime


def test_home_heatmap_is_opt_in():
    home = (ROOT / "screens" / "0_Accueil.py").read_text(encoding="utf-8")
    assert "show_home_heatmap" in home
    assert "Afficher la carte du marché" in home
    assert "Carte du marché désactivée" in home
    assert home.index("show_heatmap = st.toggle") < home.index("plotly_events(")