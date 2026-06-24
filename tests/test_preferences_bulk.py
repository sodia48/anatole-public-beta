import importlib
import tempfile


def test_preferences_are_loaded_and_saved_in_one_bundle(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ANATOLE_DATA_DIR", tmp)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        import core.config
        import core.database

        importlib.reload(core.config)
        importlib.reload(core.database)

        core.database.init_db(force=True)
        profile = core.database.ensure_profile("prefs-user")
        core.database.set_preferences(
            profile,
            {
                "theme": "dark",
                "density": "compact",
                "refresh_seconds": "120",
            },
        )

        values = core.database.get_preferences(profile)
        assert values["theme"] == "dark"
        assert values["density"] == "compact"
        assert values["refresh_seconds"] == "120"
