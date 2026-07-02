from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ecosystem_module_exists():
    module = (ROOT / "core" / "ecosystem.py").read_text(encoding="utf-8")
    assert "def ecosystem_for_ticker" in module
    assert "def ecosystem_sankey" in module


def test_ecosystem_data_exists():
    data = (ROOT / "data" / "company_ecosystem.csv").read_text(encoding="utf-8")
    assert "ticker,layer,relation,entity,category,sector,confidence,note" in data
    assert "RY.TO" in data
    assert "SHOP.TO" in data


def test_focus_has_ecosystem_section():
    focus = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")
    assert "Écosystème" in focus
    assert "ecosystem_for_ticker" in focus
    assert "ecosystem_sankey" in focus
