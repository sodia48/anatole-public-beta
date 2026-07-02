from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_volume_colors_added():
    text = (ROOT / "core" / "charts.py").read_text(encoding="utf-8")
    assert "Volume d'entrée" in text
    assert "Volume de sortie" in text
    assert "rgba(16,185,129,0.55)" in text
    assert "rgba(239,68,68,0.55)" in text


def test_focus_ownership_metrics_added():
    text = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")
    assert "Retail estimé" in text
    assert "Institutions" in text
    assert "Le retail exact n'est pas publié en temps réel" in text
