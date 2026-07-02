from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_focus_uses_auto_plotly_without_toggle():
    text = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")

    assert "Utiliser le graphique Plotly" not in text
    assert "Indicateurs Plotly avancés" not in text
    assert "DEFAULT_PLOTLY_OVERLAYS" in text
    assert "focus_plotly_auto" in text


def test_price_chart_has_default_overlays():
    text = (ROOT / "core" / "charts.py").read_text(encoding="utf-8")

    assert "DEFAULT_PLOTLY_OVERLAYS" in text
    assert "overlays = overlays or DEFAULT_PLOTLY_OVERLAYS" in text
    assert '"Bandes de Bollinger" in overlays' in text
    assert '"BB_Haut" in history' in text
