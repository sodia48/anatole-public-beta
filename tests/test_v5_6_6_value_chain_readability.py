from pathlib import Path

import pandas as pd

from core.ecosystem import ecosystem_value_chain_html


ROOT = Path(__file__).resolve().parents[1]


def test_focus_value_chain_uses_readable_component_and_summary():
    focus = (ROOT / "screens" / "14_Focus.py").read_text(encoding="utf-8")
    assert "import streamlit.components.v1 as components" in focus
    assert "ecosystem_value_chain_html" in focus
    assert "_ecosystem_summary_sentence" in focus
    assert "Sources publiques" in focus


def test_value_chain_html_exposes_evidence_and_sources():
    rows = pd.DataFrame(
        [
            {
                "layer": "Intrants",
                "relation": "Capteurs",
                "entity": "Fournisseurs de composants",
                "sector": "Industrie",
                "confidence": "Documenté",
                "source_name": "Rapport annuel",
                "source_url": "https://example.com/report",
            },
            {
                "layer": "Clients servis",
                "relation": "Solutions",
                "entity": "Opérateurs commerciaux",
                "sector": "Technologie",
                "confidence": "Indicatif",
                "source_name": "",
                "source_url": "",
            },
            {
                "layer": "Secteurs impactés",
                "relation": "Productivité",
                "entity": "Transport et logistique",
                "sector": "Économie réelle",
                "confidence": "Indicatif",
                "source_name": "",
                "source_url": "",
            },
        ]
    )

    html = ecosystem_value_chain_html(rows, "MDA.TO", "MDA Space")
    assert "Chaîne de valeur lisible" in html
    assert "Liens documentés" in html
    assert "Sources publiques" in html
    assert "Rapport annuel" in html
    assert "À documenter" in html
