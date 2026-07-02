from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_inline_universe_selector_exists():
    universe = (ROOT / "core" / "universe.py").read_text(encoding="utf-8")
    assert "def render_universe_selector_inline" in universe
    assert "TSX étendu" in universe
    assert "tsx_composite" in universe
    assert "tsx_full" in universe


def test_page_header_renders_inline_selector():
    ui = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")
    assert "render_universe_selector_inline" in ui
    assert "sky-universe-strip" in ui
