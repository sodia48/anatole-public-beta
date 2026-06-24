import tempfile

import pandas as pd


def test_sqlite_database_roundtrip(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ANATOLE_DATA_DIR", tmp)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        import importlib
        import core.config
        import core.database

        importlib.reload(core.config)
        importlib.reload(core.database)

        core.database.init_db()
        profile = core.database.ensure_profile("test-user")
        core.database.add_watchlist(profile, "AAPL")
        assert "AAPL" in core.database.get_watchlist(profile)

        core.database.replace_positions(
            profile,
            pd.DataFrame(
                [{"ticker": "RY.TO", "quantity": 2, "average_cost": 100, "notes": ""}]
            ),
        )
        assert len(core.database.get_positions(profile)) == 1

        core.database.add_feedback(
            profile,
            "Très bonne application de test.",
            rating=5,
            category="Général",
        )
        assert len(core.database.get_feedback()) == 1
