from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def test_focus_uses_components_html_for_ecosystem():
    focus = (ROOT / 'screens' / '14_Focus.py').read_text(encoding='utf-8')
    assert 'import streamlit.components.v1 as components' in focus
    assert 'components.html(' in focus

def test_mda_documented_rows_have_sources():
    df = pd.read_csv(ROOT / 'data' / 'company_ecosystem.csv').fillna('')
    mda = df[df['ticker'].str.upper() == 'MDA.TO']
    assert len(mda) >= 6
    assert (mda['confidence'] == 'Documenté').any()
    assert mda['source_url'].astype(str).str.startswith('http').any()

def test_ecosystem_tables_include_sources():
    eco = (ROOT / 'core' / 'ecosystem.py').read_text(encoding='utf-8')
    assert 'source_name' in eco
    assert 'source_url' in eco
    assert 'Lien source' in eco
