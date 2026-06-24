from core.database import ConnectionAdapter


class DummyCursor:
    def __init__(self):
        self.called = False
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def executemany(self, query, params):
        self.called = True
        self.query = query
        self.params = params


class DummyPostgresConnection:
    def __init__(self):
        self.cursor_instance = DummyCursor()

    def cursor(self):
        return self.cursor_instance


def test_postgres_executemany_uses_cursor():
    raw = DummyPostgresConnection()
    adapter = ConnectionAdapter(raw, "postgresql")
    adapter.executemany(
        "INSERT INTO test(a, b) VALUES (?, ?)",
        [(1, 2), (3, 4)],
    )

    assert raw.cursor_instance.called is True
    assert raw.cursor_instance.query == (
        "INSERT INTO test(a, b) VALUES (%s, %s)"
    )
    assert raw.cursor_instance.params == [(1, 2), (3, 4)]
