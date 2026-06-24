from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_guest_consent_is_persisted_for_all_profiles():
    text = (ROOT / "core" / "public_beta.py").read_text(encoding="utf-8")

    assert 'set_preference(profile, "legal_acceptance_version", LEGAL_VERSION)' in text
    assert 'if authenticated:' not in text
    assert 'st.query_params["anatole_guest"]' in text
    assert 'anatole_guest_mode' in text


def test_sidebar_toggles_are_saved_immediately():
    text = (ROOT / "core" / "ui.py").read_text(encoding="utf-8")

    assert "from core.preferences import hydrate_preferences, save_preferences" in text
    assert '"theme": "dark" if sidebar_pref_signature[1] else "light"' in text
    assert '"density": "compact" if sidebar_pref_signature[2] else "comfortable"' in text
    assert "save_preferences(" in text
