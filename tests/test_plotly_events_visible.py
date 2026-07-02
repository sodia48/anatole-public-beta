from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_price_chart_accepts_markers_and_price_lines():
    text = (ROOT / "core" / "charts.py").read_text(encoding="utf-8")

    assert "markers: list[dict] | None = None" in text
    assert "price_lines: list[dict] | None = None" in text
    assert "_add_plotly_event_markers(fig, history, markers)" in text
    assert "fig.add_vline" in text
    assert 'name="Événements"' in text


def test_focus_passes_events_to_plotly_chart():
    text = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")

    assert "markers=markers if show_markers else None" in text
    assert "price_lines=price_lines" in text
    assert "événement(s) affiché(s)" in text
