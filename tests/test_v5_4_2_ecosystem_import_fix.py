from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ecosystem_value_chain_html_exists():
    eco = (ROOT / "core" / "ecosystem.py").read_text(encoding="utf-8")
    assert "def ecosystem_value_chain_html" in eco


def test_focus_import_can_find_expected_name():
    focus = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")
    assert "ecosystem_value_chain_html" in focus
