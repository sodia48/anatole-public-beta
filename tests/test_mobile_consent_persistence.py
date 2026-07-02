from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_beta_has_mobile_consent_bridge():
    text = (ROOT / "core" / "public_beta.py").read_text(encoding="utf-8")

    assert "streamlit.components.v1 as components" in text
    assert "anatole_accepted" in text
    assert "localStorage" in text
    assert "patchInternalLinks" in text
    assert "_mark_legal_accepted_in_url(profile)" in text
