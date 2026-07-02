from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_value_chain_html_helper_exists():
    eco = (ROOT / 'core' / 'ecosystem.py').read_text(encoding='utf-8')
    assert 'def ecosystem_value_chain_html' in eco
    assert 'Chaîne de valeur lisible' in eco


def test_focus_uses_readable_chain_first():
    focus = (ROOT / 'screens' / '14_Focus.py').read_text(encoding='utf-8')
    assert 'ecosystem_value_chain_html' in focus
    assert 'Vue réseau expérimentale' in focus
